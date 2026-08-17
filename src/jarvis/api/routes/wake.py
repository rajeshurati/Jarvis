"""Wake-word WebSocket and full-duplex local conversation page."""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from jarvis.application.wake_service import WakeWordService
from jarvis.core.logging import get_logger

router = APIRouter(prefix="/wake", tags=["wake-word"])
logger = get_logger(__name__)


WAKE_PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Local Jarvis</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui,sans-serif; }
    body { margin:0; min-height:100vh; display:grid; place-items:center;
           background:#07111f; color:#edf7ff; }
    main { width:min(660px,calc(100% - 40px)); padding:34px; border:1px solid #29405f;
           border-radius:22px; background:#101c30; }
    h1 { margin:0 0 8px; font-size:38px; }
    .privacy { color:#91a4bf; }
    button { width:100%; padding:16px; border:0; border-radius:12px; font-size:17px;
             font-weight:750; cursor:pointer; background:#5eead4; color:#073b3a; }
    button.stop { background:#fb7185; color:#4c0519; }
    #state { margin:22px 0 10px; font-size:20px; color:#a5b4fc; }
    #score { color:#91a4bf; font-variant-numeric:tabular-nums; }
    #identity { margin-top:8px; color:#7dd3fc; }
    #result { margin-top:18px; min-height:72px; padding:18px; border-radius:12px;
              background:#070d18; white-space:pre-wrap; }
  </style>
</head>
<body><main>
  <h1>Local Jarvis</h1>
  <p class="privacy">Local wake word, transcription, screen vision, face recognition, and voice.
    Speak over Jarvis at any time to interrupt.</p>
  <button id="toggle">Start listening</button>
  <div id="state">Stopped.</div><div id="score">Wake score: 0.000</div>
  <div id="identity">Face authorization: checking...</div>
  <div id="result">Say "Hey Jarvis," then speak naturally. Follow-up questions do not need the wake word.</div>
</main>
<script>
  const toggle=document.querySelector("#toggle"),stateBox=document.querySelector("#state");
  const scoreBox=document.querySelector("#score"),resultBox=document.querySelector("#result");
  const identityBox=document.querySelector("#identity");
  let stream,context,source,processor,socket,reconnectTimer,mode="stopped",commandChunks=[];
  let preRoll=[],fallbackChunks=[],speechActive=false,silenceFrames=0,fallbackBusy=false;
  let activeAudio=null,activeAudioResolve=null,activeAudioUrl=null,speechStartedAt=0;
  let bargeFrames=0,bargePreRoll=[],commandTimer=null,commandSpeech=false;
  let commandSilenceFrames=0,commandBusy=false,noiseFloor=0.004;
  let reminderPoll=null,reminderBusy=false;

  function downsample(input,inputRate,outputRate=16000){
    if(inputRate===outputRate)return input;
    const ratio=inputRate/outputRate,length=Math.round(input.length/ratio),output=new Float32Array(length);
    for(let i=0;i<length;i+=1){const start=Math.round(i*ratio),end=Math.round((i+1)*ratio);
      let sum=0,count=0;for(let j=start;j<end&&j<input.length;j+=1){sum+=input[j];count+=1;}
      output[i]=count?sum/count:0;}return output;
  }
  function pcm16(input){const output=new Int16Array(input.length);for(let i=0;i<input.length;i+=1){
    const sample=Math.max(-1,Math.min(1,input[i]));output[i]=sample<0?sample*32768:sample*32767;}return output;}
  function wav(chunks,sampleRate){const length=chunks.reduce((n,c)=>n+c.length,0),buffer=new ArrayBuffer(44+length*2),view=new DataView(buffer);
    const text=(o,s)=>{for(let i=0;i<s.length;i+=1)view.setUint8(o+i,s.charCodeAt(i));};
    text(0,"RIFF");view.setUint32(4,36+length*2,true);text(8,"WAVE");text(12,"fmt ");
    view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
    view.setUint32(24,sampleRate,true);view.setUint32(28,sampleRate*2,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
    text(36,"data");view.setUint32(40,length*2,true);let offset=44;chunks.forEach(c=>c.forEach(s=>{
      const b=Math.max(-1,Math.min(1,s));view.setInt16(offset,b<0?b*32768:b*32767,true);offset+=2;}));
    return new Blob([buffer],{type:"audio/wav"});
  }
  async function refreshIdentity(){try{const response=await fetch("/identity/status"),data=await response.json();
    if(!response.ok)throw new Error(data.detail||"unavailable");identityBox.textContent=data.enrolled_profiles.length?
      `Face authorization: ${data.session_authorized?"authorized":"enrolled"} (${data.enrolled_profiles.join(", ")})`:
      "Face authorization: not enrolled - say 'Enroll my face'";}catch(error){identityBox.textContent=`Face authorization: ${error.message}`;}}
  async function ensureAuthorized(){const response=await fetch("/identity/status"),status=await response.json();
    if(!response.ok||!status.enrolled_profiles?.length||status.session_authorized)return;
    stateBox.textContent="Recognizing your face locally...";const check=await fetch("/identity/verify-current",{method:"POST"}),result=await check.json();
    if(!check.ok||!result.authorized)throw new Error(result.detail||"Face authorization failed");await refreshIdentity();
  }
  async function deliverDueReminders(){if(reminderBusy||mode!=="listening")return;reminderBusy=true;
    try{const response=await fetch("/reminders/claim-due",{method:"POST"});if(!response.ok)return;
      const reminders=await response.json();for(const reminder of reminders){
        resultBox.textContent=`Reminder: ${reminder.title}`;stateBox.textContent="Reminder due";
        const interrupted=await speakReply(`Reminder: ${reminder.title}`);if(interrupted)return;
        mode="listening";stateBox.textContent="Listening for Hey Jarvis...";}}
    catch(error){console.warn("Reminder delivery failed",error);}finally{reminderBusy=false;}}
  function beginCommandWindow(label="Listening for your follow-up...",initial=[]){clearTimeout(commandTimer);
    commandChunks=initial.map(chunk=>new Float32Array(chunk));commandSpeech=initial.length>0;commandSilenceFrames=0;mode="command";
    stateBox.textContent=label;commandTimer=setTimeout(()=>void finishCommand(),7000);
  }
  function interruptSpeech(){if(!activeAudio||!activeAudioResolve)return;
    const initial=bargePreRoll.map(chunk=>new Float32Array(chunk)),resolve=activeAudioResolve;
    activeAudioResolve=null;activeAudio.pause();resolve();beginCommandWindow("I stopped. Keep speaking...",initial);
  }
  async function speakReply(text){const response=await fetch("/assistant/speak",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    if(!response.ok){const error=await response.json();throw new Error(error.detail||"Speech failed");}
    const url=URL.createObjectURL(await response.blob()),audio=new Audio(url);activeAudio=audio;activeAudioUrl=url;
    speechStartedAt=performance.now();bargeFrames=0;bargePreRoll=[];mode="speaking";let interrupted=false;
    try{await new Promise((resolve,reject)=>{activeAudioResolve=()=>{interrupted=true;resolve();};audio.onended=resolve;
      audio.onerror=()=>reject(new Error("Audio playback failed"));audio.play().catch(reject);});return interrupted;}
    finally{audio.pause();activeAudio=null;activeAudioResolve=null;if(activeAudioUrl)URL.revokeObjectURL(activeAudioUrl);activeAudioUrl=null;}
  }
  function conversationSafe(text){const cleaned=String(text||"").replace(/[*_`>#]/g,"").replace(/\\s+/g," ").trim();
    if(!cleaned)return "I did not get a useful answer.";const words=cleaned.split(" ");if(words.length<=28)return cleaned;
    const dangling=new Set(["and","or","but","with","including","which","that","for","to","of","in","on","via","like","showing"]);
    let kept=words.slice(0,28);while(kept.length&&dangling.has(kept.at(-1).replace(/[^a-z]/gi,"").toLowerCase()))kept.pop();
    return `${kept.join(" ").replace(/[,;:\\-]+$/,"")}.`;}
  async function respondToText(text){resultBox.textContent=`You: ${text}\n\nJarvis is thinking...`;stateBox.textContent="Thinking locally...";
    await ensureAuthorized();const answer=await fetch("/assistant/respond",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    const reply=await answer.json();if(!answer.ok)throw new Error(reply.detail||"Assistant failed");
    const safeReply=conversationSafe(reply.reply);resultBox.textContent=`You: ${text}\n\nJarvis: ${safeReply}`;stateBox.textContent="Speaking - interrupt me anytime...";
    const interrupted=await speakReply(safeReply);await refreshIdentity();if(!interrupted&&mode!=="command")beginCommandWindow();
  }
  async function finishCommand(){if(commandBusy)return;commandBusy=true;clearTimeout(commandTimer);mode="transcribing";stateBox.textContent="Transcribing locally...";
    const form=new FormData();form.append("audio",wav(commandChunks,context.sampleRate),"command.wav");commandChunks=[];
    try{const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000);
      const response=await fetch("/voice/transcribe-upload",{method:"POST",body:form,signal:controller.signal});clearTimeout(timer);
      const data=await response.json();if(!response.ok)throw new Error(data.detail||"Transcription failed");
      if(!data.text){resultBox.textContent="Conversation paused. Say Hey Jarvis when you need me.";return;}
      await respondToText(data.text);
    }catch(error){resultBox.textContent=error.message;}finally{commandBusy=false;if(mode!=="command"&&mode!=="speaking"){
      mode="listening";stateBox.textContent="Listening for Hey Jarvis...";}}
  }
  async function acknowledgeWake(){mode="acknowledging";speechActive=false;fallbackChunks=[];stateBox.textContent="Wake word detected";
    try{await speakReply("Yes?");}catch(error){resultBox.textContent=`Voice acknowledgement failed: ${error.message}`;}
    if(mode!=="command")beginCommandWindow("Listening for your command...");resultBox.textContent="Speak now...";
  }
  async function checkFallbackWake(chunks){fallbackBusy=true;mode="checking";stateBox.textContent="Checking spoken wake phrase locally...";
    try{const form=new FormData();form.append("audio",wav(chunks,context.sampleRate),"wake-phrase.wav");
      const response=await fetch("/voice/transcribe-upload",{method:"POST",body:form}),data=await response.json();
      if(!response.ok)throw new Error(data.detail||"Wake phrase check failed");const text=(data.text||"").trim(),lower=text.toLowerCase();
      const index=lower.lastIndexOf("jarvis");if(index<0){mode="listening";stateBox.textContent="Listening for Hey Jarvis...";return;}
      const command=text.slice(index+6).replace(/^[\\s,.:;!?-]+/,"").trim();
      if(command){mode="responding";await respondToText(command);if(mode!=="command"){mode="listening";stateBox.textContent="Listening for Hey Jarvis...";}}
      else await acknowledgeWake();
    }catch(error){resultBox.textContent=error.message;mode="listening";stateBox.textContent="Listening for Hey Jarvis...";}
    finally{fallbackBusy=false;}
  }
  function connectWakeSocket(){socket=new WebSocket(`${location.protocol==="https:"?"wss":"ws"}://${location.host}/wake/ws`);socket.binaryType="arraybuffer";
    socket.onopen=()=>{if(mode==="listening")stateBox.textContent="Listening for Hey Jarvis...";};
    socket.onmessage=event=>{const message=JSON.parse(event.data);if(message.type==="score")scoreBox.textContent=`Wake score: ${message.score.toFixed(3)}`;
      if(message.type==="detected"&&mode==="listening")void acknowledgeWake();};socket.onerror=()=>socket.close();
    socket.onclose=()=>{if(mode!=="stopped"){stateBox.textContent="Reconnecting local listener...";clearTimeout(reconnectTimer);
      reconnectTimer=setTimeout(connectWakeSocket,1000);}};
  }
  async function start(){const nativeStatus=await fetch("/voice/runtime-status").then(response=>response.json()).catch(()=>({running:false,enabled:false}));
    if(nativeStatus.running&&nativeStatus.enabled)throw new Error("Background Jarvis is already listening. Use this page only after pausing background listening in the tray control center.");
    stream=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:false}});
    context=new AudioContext();source=context.createMediaStreamSource(stream);processor=context.createScriptProcessor(4096,1,1);connectWakeSocket();
    processor.onaudioprocess=event=>{const samples=new Float32Array(event.inputBuffer.getChannelData(0));
      let energy=0;for(let i=0;i<samples.length;i+=1)energy+=samples[i]*samples[i];const rms=Math.sqrt(energy/samples.length);
      if(mode==="listening"){if(socket?.readyState===WebSocket.OPEN)socket.send(pcm16(downsample(samples,context.sampleRate)).buffer);
        if(rms<0.012)noiseFloor=noiseFloor*0.95+rms*0.05;scoreBox.textContent=`Mic level: ${rms.toFixed(3)}`;
        preRoll.push(samples);if(preRoll.length>5)preRoll.shift();
        if(!fallbackBusy&&rms>0.012&&!speechActive){speechActive=true;fallbackChunks=preRoll.map(chunk=>new Float32Array(chunk));silenceFrames=0;}
        else if(!fallbackBusy&&speechActive){fallbackChunks.push(samples);silenceFrames=rms<0.008?silenceFrames+1:0;
          if((silenceFrames>=8&&fallbackChunks.length>=10)||fallbackChunks.length>=70){const utterance=fallbackChunks;speechActive=false;fallbackChunks=[];void checkFallbackWake(utterance);}}}
      else if(mode==="command"){commandChunks.push(samples);const threshold=Math.max(0.012,noiseFloor*3);
        if(rms>threshold){commandSpeech=true;commandSilenceFrames=0;}else if(commandSpeech&&rms<0.009)commandSilenceFrames+=1;
        if(commandSpeech&&commandSilenceFrames>=8&&commandChunks.length>=10)void finishCommand();}
      else if(mode==="speaking"){bargePreRoll.push(samples);if(bargePreRoll.length>6)bargePreRoll.shift();
        const threshold=Math.max(0.010,noiseFloor*3);if(performance.now()-speechStartedAt>350&&rms>threshold)bargeFrames+=1;else bargeFrames=Math.max(0,bargeFrames-1);
        if(bargeFrames>=2)interruptSpeech();}};
    source.connect(processor);processor.connect(context.destination);mode="listening";toggle.textContent="Stop listening";toggle.className="stop";
    stateBox.textContent="Listening for Hey Jarvis...";await refreshIdentity();clearInterval(reminderPoll);
    reminderPoll=setInterval(()=>void deliverDueReminders(),2000);void deliverDueReminders();
  }
  async function stop(){mode="stopped";clearTimeout(reconnectTimer);clearTimeout(commandTimer);clearInterval(reminderPoll);if(activeAudio)activeAudio.pause();
    if(activeAudioResolve){const resolve=activeAudioResolve;activeAudioResolve=null;resolve();}if(processor)processor.disconnect();if(source)source.disconnect();if(socket)socket.close();
    if(context)await context.close();if(stream)stream.getTracks().forEach(track=>track.stop());toggle.textContent="Start listening";toggle.className="";stateBox.textContent="Stopped.";
  }
  toggle.addEventListener("click",async()=>{toggle.disabled=true;try{if(mode==="stopped")await start();else await stop();}
    catch(error){resultBox.textContent=error.message;await stop();}finally{toggle.disabled=false;}});
  window.addEventListener("load",async()=>{await refreshIdentity();try{const nativeStatus=await fetch("/voice/runtime-status").then(response=>response.json());
    if(nativeStatus.running&&nativeStatus.enabled){toggle.textContent="Background listening active";toggle.disabled=true;
      stateBox.textContent="Background Jarvis is listening - this browser microphone is off.";
      resultBox.textContent="Speak normally after saying Hey Jarvis. Close this page if you want; the tray assistant stays active.";}}
    catch(error){resultBox.textContent="Background status is unavailable. You can use Start listening as a fallback.";}});
</script></body></html>"""


@router.get("", response_class=HTMLResponse)
async def wake_page() -> HTMLResponse:
    """Return the local always-listening control page."""
    return HTMLResponse(WAKE_PAGE)


@router.websocket("/ws")
async def wake_socket(websocket: WebSocket) -> None:
    """Score streamed 16 kHz PCM and emit wake events."""
    service: WakeWordService | None = websocket.app.state.wake_service
    await websocket.accept()
    if service is None:
        await websocket.send_json({"type": "error", "detail": "Wake service unavailable"})
        await websocket.close(code=1011)
        return
    await service.reset()
    frame_count = 0
    try:
        while True:
            detected, score = await service.process_pcm(await websocket.receive_bytes())
            frame_count += 1
            if detected:
                await websocket.send_json({"type": "detected", "score": score})
            elif frame_count % 4 == 0:
                await websocket.send_json({"type": "score", "score": score})
    except WebSocketDisconnect:
        return
    except Exception:
        logger.exception("wake_word_inference_failed")
        await websocket.close(code=1011, reason="Local wake-word inference failed")
