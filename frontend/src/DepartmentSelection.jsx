import { useCallback, useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import VoiceOrb from "./VoiceOrb";
import { isCancelCommand, normaliseVoiceText, useVoiceFlow, voiceYesNo } from "./voiceFlow";

const DEPARTMENTS = [
  { en:"Kayachikitsa", hi:"कायचिकित्सा", value:"Kayachikitsa", words:["kayachikitsa","kaya chikitsa","कायचिकित्सा"] },
  { en:"Panchakarma", hi:"पंचकर्म", value:"Panchakarma", words:["panchakarma","panch karma","पंचकर्म"] },
  { en:"Shalya", hi:"शल्य", value:"Shalya", words:["shalya","surgery","शल्य"] },
  { en:"Prasuti Tantra", hi:"प्रसूति तंत्र", value:"Prasuti Tantra", words:["prasuti","prasoothi","pregnancy","women","प्रसूति"] },
  { en:"General consultation", hi:"सामान्य परामर्श", value:"general", words:["general","not sure","don't know","dont know","samanya","pata nahi","सामान्य","पता नहीं"] },
];
const PROMPTS = { en:"Which department are you visiting? Say Kayachikitsa, Panchakarma, Shalya, Prasuti Tantra, or General if you are not sure.", hi:"आप किस विभाग में आए हैं? कायचिकित्सा, पंचकर्म, शल्य, प्रसूति तंत्र, या निश्चित न होने पर सामान्य कहें।" };

function DepartmentSelection({ language, interactionMode, onSelect, onBack, onClearData }) {
  const isSpeak = interactionMode === "speak";
  const isHindi = language === "hi";
  const voice = useVoiceFlow(language);
  const [candidate, setCandidate] = useState(null);
  const startedRef = useRef(false);

  const confirmCancel = useCallback(async () => {
    let answer = await voice.promptAndListen(isHindi ? "क्या आप वाकई रद्द करके अपना डेटा मिटाना चाहते हैं? हाँ या नहीं कहें।" : "Are you sure you want to cancel and clear your data? Say yes or no.").catch(()=>"");
    if (voiceYesNo(answer) === null) answer = await voice.promptAndListen(isHindi ? "मैं समझ नहीं पाया। हाँ या नहीं कहें।" : "I did not understand. Please say yes or no.", { retries: 0 }).catch(()=>"");
    if (voiceYesNo(answer) === true) onClearData();
    else if (voiceYesNo(answer) === false) await voice.speak(isHindi ? "ठीक है, विभाग चयन जारी रखें।" : "Okay, we will continue choosing a department.");
  }, [isHindi, onClearData, voice.promptAndListen, voice.speak]);

  const hearDepartment = useCallback(async (answer, attempt = 0) => {
    if (isCancelCommand(answer)) return confirmCancel();
    const text=normaliseVoiceText(answer);
    const match=DEPARTMENTS.find((item)=>item.words.some((word)=>text.includes(word)));
    if (!match) {
      if (attempt >= 2) {
        voice.setError(isHindi ? "कृपया स्क्रीन से विभाग चुनें।" : "Please choose a department on the screen.");
        return;
      }
      const retry = await voice.promptAndListen(isHindi ? "मैं विभाग नहीं समझ पाया। कृपया फिर से बोलें।" : "I did not understand the department. Please speak again.").catch(()=>"");
      if (retry) return hearDepartment(retry, attempt + 1);
      return;
    }
    setCandidate(match);
    const confirmation=await voice.promptAndListen(isHindi ? `आपने ${match.hi} चुना है। क्या यह सही है?` : `You selected ${match.en}. Is that correct?`).catch(()=>"");
    if (isCancelCommand(confirmation)) return confirmCancel();
    if (voiceYesNo(confirmation) === true) onSelect(match.value);
    else if (voiceYesNo(confirmation) === false) { setCandidate(null); const retry=await voice.promptAndListen(PROMPTS[language] || PROMPTS.en).catch(()=>""); return hearDepartment(retry); }
    else {
      const retry = await voice.promptAndListen(isHindi ? "मैं समझ नहीं पाया। हाँ या नहीं कहें।" : "I did not understand. Please say yes or no.").catch(()=>"");
      if (voiceYesNo(retry) === true) onSelect(match.value);
      else if (voiceYesNo(retry) === false) { setCandidate(null); const next = await voice.promptAndListen(PROMPTS[language] || PROMPTS.en).catch(()=>""); if (next) return hearDepartment(next); }
    }
  }, [confirmCancel, isHindi, language, onSelect, voice.promptAndListen, voice.setError]);

  useEffect(()=>{
    if (!isSpeak || startedRef.current) return;
    startedRef.current=true;
    void voice.promptAndListen(PROMPTS[language] || PROMPTS.en, { timeoutMs:8000 }).then(hearDepartment).catch(()=>{});
  },[hearDepartment,isSpeak,language,voice.promptAndListen]);

  const chooseByTouch = async (item) => {
    if (!isSpeak) return onSelect(item.value);
    voice.cancel();
    setCandidate(item);
    const answer=await voice.promptAndListen(isHindi ? `आपने ${item.hi} चुना है। क्या यह सही है?` : `You selected ${item.en}. Is that correct?`).catch(()=>"");
    if (voiceYesNo(answer) === true) onSelect(item.value);
    else if (voiceYesNo(answer) === false) setCandidate(null);
    else {
      const retry = await voice.promptAndListen(isHindi ? "मैं समझ नहीं पाया। हाँ या नहीं कहें।" : "I did not understand. Please say yes or no.").catch(()=>"");
      if (voiceYesNo(retry) === true) onSelect(item.value);
      else setCandidate(null);
    }
  };
  const label=voice.state === "listening" ? (isHindi?"सुन रहा है":"Listening") : voice.state === "speaking" ? (isHindi?"बोल रहा है":"Speaking") : voice.state === "thinking" ? (isHindi?"समझ रहा है":"Understanding") : candidate ? (isHindi?"पुष्टि करें":"Confirm selection") : (isHindi?"विभाग चुनें":"Choose a department");
  return <main className="start-shell voice-form-shell"><section className="start-card department-card" aria-label="Department selection">
    <p className="start-eyebrow">MediKiosk · {isHindi?"विभाग":"Department"}</p>
    {isSpeak && <VoiceOrb compact state={voice.state} label={label}/>}<h1>{isHindi?"आज आपको किस विभाग में जाना है?":"Which department do you need today?"}</h1>
    <div className="department-grid">{DEPARTMENTS.map((item)=><button className={`department-button ${candidate?.value===item.value?"selected":""}`} type="button" key={item.value} onClick={()=>void chooseByTouch(item)}>{isHindi?item.hi:item.en}</button>)}</div>
    {isSpeak && <p className="live-caption" aria-live="polite">{voice.caption}</p>}{voice.error&&<p className="language-error" role="alert">{voice.error}</p>}
    {isSpeak&&<button className="voice-choice-button" type="button" onClick={()=>voice.state==="listening"?voice.stopListening():void voice.listen(language,8000).then(hearDepartment).catch(()=>{})}>{voice.state==="listening"?(isHindi?"सुनना बंद करें":"Stop listening"):(isHindi?"🎙 विभाग बोलें":"🎙 Say department")}</button>}
    <button className="secondary-start-button" type="button" onClick={onBack}>{isHindi?"रोगी पहचान पर वापस":"Back to patient identification"}</button><ClearDataButton language={language} onClearData={onClearData}/>
  </section></main>;
}
export default DepartmentSelection;
