import { useCallback, useEffect, useRef, useState } from "react";
import ClearDataButton from "./ClearDataButton";
import { apiFetch, patientHeaders } from "./api";
import VoiceOrb from "./VoiceOrb";
import { isCancelCommand, normaliseVoiceText, useVoiceFlow, voiceYesNo } from "./voiceFlow";

const COPY = {
  en: {
    visited: "Have you visited us before? Say yes if you have a Medi ID, or no if this is your first visit.",
    name: "Please say your full name.", nameConfirm: (value) => `I heard ${value}. Is that correct?`,
    phone: "Please say your ten digit phone number.", phoneConfirm: (value) => `I heard ${value}. Is that correct?`,
    abha: "Would you like to add your ABHA details? Say yes or no.",
    medi: "Please say your Medi ID, including the letters M K.",
    cancel: "Are you sure you want to cancel and clear your data? Say yes or no.",
    unclear: "I did not understand. Please try again or use the screen.",
  },
  hi: {
    visited: "क्या आप पहले हमारे यहाँ आ चुके हैं? अगर आपके पास मेडी आईडी है तो हाँ कहें, पहली मुलाकात है तो नहीं कहें।",
    name: "कृपया अपना पूरा नाम बोलें।", nameConfirm: (value) => `मैंने ${value} सुना। क्या यह सही है?`,
    phone: "कृपया अपना दस अंकों का फ़ोन नंबर बोलें।", phoneConfirm: (value) => `मैंने ${value} सुना। क्या यह सही है?`,
    abha: "क्या आप अपना आभा विवरण जोड़ना चाहेंगे? हाँ या नहीं कहें।",
    medi: "कृपया अक्षर एम के सहित अपनी मेडी आईडी बोलें।",
    cancel: "क्या आप वाकई रद्द करके अपना डेटा मिटाना चाहते हैं? हाँ या नहीं कहें।",
    unclear: "मैं समझ नहीं पाया। फिर से बोलें या स्क्रीन का उपयोग करें।",
  },
};

const DIGITS = { zero:"0",oh:"0",one:"1",two:"2",to:"2",too:"2",three:"3",four:"4",for:"4",five:"5",six:"6",seven:"7",eight:"8",ate:"8",nine:"9", शून्य:"0",एक:"1",दो:"2",तीन:"3",चार:"4",पांच:"5",पाँच:"5",छह:"6",सात:"7",आठ:"8",नौ:"9" };
function spokenDigits(value) {
  const direct = value.replace(/\D/g, "");
  if (direct.length >= 6) return direct.slice(0, 10);
  return normaliseVoiceText(value).split(" ").map((part) => DIGITS[part] || "").join("").slice(0, 10);
}
function formatPhone(value) {
  const digits = spokenDigits(value);
  return digits.length > 5 ? `${digits.slice(0, 5)}-${digits.slice(5)}` : digits;
}
function normaliseMediId(value) {
  const compact = value.toUpperCase().replace(/\b(EM|M)\s*KAY\b/g, "MK").replace(/[^A-Z0-9]/g, "");
  const body = compact.startsWith("MK") ? compact.slice(2) : compact;
  return `MK-${body.slice(0, 6)}`;
}

function PatientIdentification({ language, interactionMode, sessionId, sessionToken, onComplete, onBack, onClearData }) {
  const isSpeak = interactionMode === "speak";
  const isHindi = language === "hi";
  const copy = COPY[language] || COPY.en;
  const voice = useVoiceFlow(language);
  const [step, setStep] = useState("question");
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [abhaNumber, setAbhaNumber] = useState("");
  const [abhaAddress, setAbhaAddress] = useState("");
  const [mediId, setMediId] = useState("");
  const [failedAttempts, setFailedAttempts] = useState(0);
  const [voiceRetries, setVoiceRetries] = useState({ name: 0, phone: 0, medi: 0 });
  const [registeredId, setRegisteredId] = useState("");
  const [foundPatient, setFoundPatient] = useState(null);
  const [error, setError] = useState("");
  const [isBusy, setIsBusy] = useState(false);
  const actionRef = useRef(null);
  const stepRunRef = useRef("");

  useEffect(() => () => actionRef.current?.abort(), []);

  const confirmCancel = useCallback(async () => {
    try {
      const answer = await voice.promptAndListen(copy.cancel);
      if (voiceYesNo(answer) === true) onClearData();
      else if (voiceYesNo(answer) === false) await voice.speak(isHindi ? "ठीक है, हम जारी रखेंगे।" : "Okay, we will keep going.");
      else voice.setError(copy.unclear);
    } catch { /* Typed controls remain available. */ }
  }, [copy, isHindi, onClearData, voice.promptAndListen, voice.setError, voice.speak]);

  const interceptCommand = useCallback((answer) => {
    if (!isCancelCommand(answer)) return false;
    void confirmCancel();
    return true;
  }, [confirmCancel]);

  const register = useCallback(async () => {
    if (name.trim().length < 2 || spokenDigits(phone).length !== 10) {
      setError(isHindi ? "कृपया नाम और सही दस अंकों का फ़ोन नंबर दर्ज करें।" : "Please enter a name and a valid ten-digit phone number.");
      return;
    }
    setIsBusy(true); setError("");
    const controller = new AbortController(); actionRef.current?.abort(); actionRef.current = controller;
    try {
      const response = await apiFetch("/patients/register", { method:"POST", headers:patientHeaders(sessionId, sessionToken, true), body:JSON.stringify({ name:name.trim(), phone_number:spokenDigits(phone), abha_number:abhaNumber.replace(/\D/g,""), abha_address:abhaAddress.trim() }), signal:controller.signal }, 10000);
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Registration failed.");
      setRegisteredId(result.medi_id); setStep("registered");
    } catch (requestError) { if (!controller.signal.aborted) setError(requestError.message || "Registration failed."); }
    finally { if (!controller.signal.aborted) setIsBusy(false); }
  }, [abhaAddress, abhaNumber, isHindi, name, phone, sessionId, sessionToken]);

  const lookup = useCallback(async (rawId) => {
    const id = normaliseMediId(rawId || mediId); setMediId(id); setIsBusy(true); setError("");
    const controller = new AbortController(); actionRef.current?.abort(); actionRef.current = controller;
    try {
      const response = await apiFetch(`/patients/${encodeURIComponent(id)}`, { headers:patientHeaders(sessionId, sessionToken), signal:controller.signal }, 10000);
      const result = await response.json();
      if (!response.ok) {
        if (response.status !== 404) throw new Error(result.detail || "Patient lookup is unavailable.");
        const attempts = failedAttempts + 1; setFailedAttempts(attempts);
        if (attempts >= 3) setStep("lookup-create");
        else { setError(isHindi ? `मेडी आईडी नहीं मिली। ${3-attempts} प्रयास बाकी हैं।` : `Medi ID not found. ${3-attempts} attempt${3-attempts === 1 ? "" : "s"} remaining.`); setStep("returning-retry"); }
        return;
      }
      setFoundPatient({ medi_id:result.medi_id, name:result.name, phone_number:result.phone_number, abha_number:result.abha_number, abha_address:result.abha_address, abha_status:result.abha_status, prakriti:result.prakriti, returning_patient:true });
      setStep("welcome");
    } catch (requestError) { if (!controller.signal.aborted) setError(requestError.message || "Unable to find that Medi ID."); }
    finally { if (!controller.signal.aborted) setIsBusy(false); }
  }, [failedAttempts, isHindi, mediId, sessionId, sessionToken]);

  useEffect(() => {
    if (!isSpeak || isBusy || stepRunRef.current === step) return;
    stepRunRef.current = step;
    (async () => {
      let answer;
      if (step === "question") {
        answer = await voice.promptAndListen(copy.visited); if (interceptCommand(answer)) return;
        const choice = voiceYesNo(answer); if (choice === true) setStep("returning"); else if (choice === false) setStep("name"); else { voice.setError(copy.unclear); stepRunRef.current = ""; }
      } else if (step === "name") {
        answer = await voice.promptAndListen(copy.name); if (interceptCommand(answer)) return;
        if (answer.trim().length < 2) { voice.setError(copy.unclear); stepRunRef.current = ""; return; }
        setName(answer.trim()); setStep("confirm-name");
      } else if (step === "confirm-name") {
        answer = await voice.promptAndListen(copy.nameConfirm(name)); if (interceptCommand(answer)) return;
        const choice = voiceYesNo(answer); if (choice === true) setStep("phone"); else if (choice === false) { const count=voiceRetries.name+1; setVoiceRetries((v)=>({...v,name:count})); setStep(count >= 3 ? "name-type" : "name"); } else { voice.setError(copy.unclear); stepRunRef.current=""; }
      } else if (step === "phone") {
        answer = await voice.promptAndListen(copy.phone, { timeoutMs:8500 }); if (interceptCommand(answer)) return;
        const value=formatPhone(answer); if (spokenDigits(value).length !== 10) { const count=voiceRetries.phone+1; setVoiceRetries((v)=>({...v,phone:count})); setStep(count >= 3 ? "phone-type" : "phone-retry"); } else { setPhone(value); setStep("confirm-phone"); }
      } else if (step === "phone-retry") setStep("phone");
      else if (step === "confirm-phone") {
        answer = await voice.promptAndListen(copy.phoneConfirm(phone.split("").join(" ")), { timeoutMs:6000 }); if (interceptCommand(answer)) return;
        const choice=voiceYesNo(answer); if (choice === true) setStep("abha-choice"); else if (choice === false) { const count=voiceRetries.phone+1; setVoiceRetries((v)=>({...v,phone:count})); setStep(count >= 3 ? "phone-type" : "phone"); } else { voice.setError(copy.unclear); stepRunRef.current=""; }
      } else if (step === "abha-choice") {
        answer=await voice.promptAndListen(copy.abha); if (interceptCommand(answer)) return;
        const choice=voiceYesNo(answer); if (choice === true) setStep("abha"); else if (choice === false) await register(); else { voice.setError(copy.unclear); stepRunRef.current=""; }
      } else if (step === "returning" || step === "returning-retry") {
        answer=await voice.promptAndListen(step === "returning" ? copy.medi : (isHindi ? "मेडी आईडी नहीं मिली। कृपया फिर से बोलें।" : "That Medi ID was not found. Please say it again."), { timeoutMs:8000 }); if (interceptCommand(answer)) return;
        if (!answer) return; await lookup(answer);
      } else if (step === "lookup-create") {
        answer=await voice.promptAndListen(isHindi ? "तीन प्रयासों के बाद मेडी आईडी नहीं मिली। क्या आप नई मेडी आईडी बनाना चाहेंगे?" : "We could not find the Medi ID after three attempts. Would you like to create a new Medi ID?");
        if (voiceYesNo(answer) === true) { setFailedAttempts(0); setMediId(""); setStep("name"); } else if (voiceYesNo(answer) === false) await voice.speak(isHindi ? "ठीक है। कृपया स्टाफ से सहायता लें।" : "Okay. Please ask a staff member for help."); else { voice.setError(copy.unclear); stepRunRef.current=""; }
      } else if (step === "welcome") {
        await voice.speak(isHindi ? `फिर से स्वागत है, ${foundPatient?.name}। आपका विवरण मिल गया है।` : `Welcome back, ${foundPatient?.name}. We found your details.`); onComplete(foundPatient);
      } else if (step === "registered") {
        answer=await voice.promptAndListen(isHindi ? `आपकी मेडी आईडी ${registeredId.split("").join(" ")} है। इसे सुरक्षित रखें। आगे बढ़ने के लिए हाँ कहें।` : `Your Medi ID is ${registeredId.split("").join(" ")}. Please keep it safe. Say yes to continue.`, { timeoutMs:8000 });
        if (voiceYesNo(answer) === true || normaliseVoiceText(answer).includes("continue")) onComplete({ medi_id:registeredId, name:name.trim(), phone_number:spokenDigits(phone), abha_status:abhaNumber ? "patient_provided" : "not_linked", prakriti:null, returning_patient:false }); else { voice.setError(copy.unclear); stepRunRef.current=""; }
      }
    })().catch(() => {
      if (["name", "confirm-name"].includes(step)) {
        const count = voiceRetries.name + 1; setVoiceRetries((value)=>({...value,name:count}));
        if (count >= 3) setStep("name-type"); else stepRunRef.current = "";
      } else if (["phone", "phone-retry", "confirm-phone"].includes(step)) {
        const count = voiceRetries.phone + 1; setVoiceRetries((value)=>({...value,phone:count}));
        if (count >= 3) setStep("phone-type"); else stepRunRef.current = "";
      } else if (["returning", "returning-retry"].includes(step)) {
        const count = voiceRetries.medi + 1; setVoiceRetries((value)=>({...value,medi:count}));
        if (count >= 3) setStep("medi-type"); else stepRunRef.current = "";
      } else stepRunRef.current = "";
    });
  }, [abhaNumber, copy, failedAttempts, foundPatient, interceptCommand, isBusy, isHindi, isSpeak, lookup, name, onComplete, phone, register, registeredId, step, voice.promptAndListen, voice.setError, voice.speak, voiceRetries]);

  function manualRegister(event) { event.preventDefault(); void register(); }
  const orbLabel = voice.state === "listening" ? (isHindi ? "सुन रहा है" : "Listening") : voice.state === "speaking" ? (isHindi ? "बोल रहा है" : "Speaking") : voice.state === "thinking" ? (isHindi ? "समझ रहा है" : "Understanding") : (isHindi ? "तैयार" : "Ready");
  const showNewForm = ["name-type","phone-type","abha"].includes(step) || (!isSpeak && step === "new");
  const showReturningForm = step === "medi-type" || (!isSpeak && step === "returning");
  const voiceStepHeading = {
    name: isHindi ? "अपना नाम बोलें" : "Tell us your name",
    "confirm-name": isHindi ? "अपने नाम की पुष्टि करें" : "Confirm your name",
    phone: isHindi ? "अपना फ़ोन नंबर बोलें" : "Tell us your phone number",
    "phone-retry": isHindi ? "फ़ोन नंबर फिर से बोलें" : "Try the phone number again",
    "confirm-phone": isHindi ? "अपने फ़ोन नंबर की पुष्टि करें" : "Confirm your phone number",
    "abha-choice": isHindi ? "वैकल्पिक ABHA" : "Optional ABHA details",
    returning: isHindi ? "अपनी मेडी आईडी बोलें" : "Say your Medi ID",
    "returning-retry": isHindi ? "मेडी आईडी फिर से बोलें" : "Try your Medi ID again",
  }[step];

  return <main className="start-shell voice-form-shell"><section className="start-card patient-id-card" aria-label="Patient identification">
    <p className="start-eyebrow">MediKiosk · {isHindi ? "रोगी की पहचान" : "Patient identification"}</p>
    {isSpeak && <VoiceOrb compact state={voice.state} label={orbLabel} />}
    {voiceStepHeading && <h1>{voiceStepHeading}</h1>}
    {step === "question" && <><h1>{isHindi ? "क्या आप पहले आए हैं?" : "Have you visited us before?"}</h1><div className="language-buttons patient-choice-buttons"><button className="language-button" onClick={()=>{voice.cancel();setStep("returning");}}>{isHindi ? "हाँ, मेडी आईडी है" : "Yes, I have a Medi ID"}</button><button className="language-button" onClick={()=>{voice.cancel();setStep(isSpeak ? "name" : "new");}}>{isHindi ? "नहीं, पहली मुलाकात" : "No, first visit"}</button></div></>}
    {showReturningForm && <><h1>{isHindi ? "अपनी मेडी आईडी दर्ज करें" : "Enter your Medi ID"}</h1><p className="start-copy">{step === "medi-type" ? (isHindi ? "आवाज़ स्पष्ट नहीं थी। टच कीबोर्ड का उपयोग करें।" : "Voice capture was not clear. Use the touch keyboard.") : ""}</p><form className="patient-form" onSubmit={(e)=>{e.preventDefault();void lookup();}}><label>Medi ID<input value={mediId} onChange={(e)=>setMediId(e.target.value)} placeholder="MK-ABC123" /></label><button className="start-button" disabled={isBusy || failedAttempts>=3}>{isBusy ? "Checking…" : "Find Medi ID"}</button></form></>}
    {showNewForm && <><h1>{isHindi ? "अपनी मेडी आईडी बनाएँ" : "Create your Medi ID"}</h1><p className="start-copy">{step === "name-type" ? (isHindi ? "आवाज़ स्पष्ट नहीं थी। कृपया नाम टाइप करें।" : "Voice capture was not clear. Please type your name.") : step === "phone-type" ? (isHindi ? "कृपया फ़ोन नंबर टाइप करें।" : "Please type your phone number.") : (isHindi ? "ABHA वैकल्पिक है और कर्मचारी इसे सत्यापित करेगा।" : "ABHA is optional and must be verified by staff.")}</p><form className="patient-form" onSubmit={manualRegister}><label>{isHindi ? "नाम" : "Name"}<input value={name} onChange={(e)=>setName(e.target.value)} /></label><label>{isHindi ? "फ़ोन नंबर" : "Phone number"}<input value={phone} onChange={(e)=>setPhone(formatPhone(e.target.value))} inputMode="numeric" placeholder="XXXXX-XXXXX" maxLength="11" /></label><details open={step === "abha"} className="abha-optional-fields"><summary>{isHindi ? "ABHA जोड़ें (वैकल्पिक)" : "Add ABHA (optional)"}</summary><label>ABHA number<input value={abhaNumber} onChange={(e)=>setAbhaNumber(e.target.value.replace(/\D/g,"").slice(0,14))} inputMode="numeric" /></label><label>ABHA address<input value={abhaAddress} onChange={(e)=>setAbhaAddress(e.target.value.toLowerCase())} placeholder="name@abdm" /></label></details><button className="start-button" disabled={isBusy}>{isBusy ? (isHindi ? "बन रहा है…" : "Creating…") : (isHindi ? "मेडी आईडी बनाएँ" : "Create Medi ID")}</button></form></>}
    {step === "abha" && isSpeak && <button className="field-voice-button" onClick={()=>void register()}>{isHindi ? "ABHA छोड़ें और आगे बढ़ें" : "Skip ABHA and continue"}</button>}
    {step === "lookup-create" && <><h1>{isHindi ? "मेडी आईडी नहीं मिली" : "Medi ID not found"}</h1><p className="start-copy">{isHindi ? "क्या आप नई मेडी आईडी बनाना चाहेंगे?" : "Would you like to create a new Medi ID?"}</p><div className="language-buttons"><button className="language-button" onClick={()=>{setFailedAttempts(0);setStep(isSpeak?"name":"new");}}>Yes</button><button className="language-button" onClick={()=>setError(isHindi?"कृपया स्टाफ से सहायता लें।":"Please ask staff for help.")}>No</button></div></>}
    {step === "registered" && <><h1>{isHindi ? "आपकी मेडी आईडी" : "Your Medi ID"}</h1><p className="medi-id-value">{registeredId}</p><button className="start-button" onClick={()=>onComplete({medi_id:registeredId,name:name.trim(),phone_number:spokenDigits(phone),abha_status:abhaNumber?"patient_provided":"not_linked",prakriti:null,returning_patient:false})}>{isHindi ? "आगे बढ़ें" : "Continue"}</button></>}
    {step === "welcome" && <><h1>{isHindi ? `फिर से स्वागत है, ${foundPatient?.name}` : `Welcome back, ${foundPatient?.name}`}</h1><button className="start-button" onClick={()=>onComplete(foundPatient)}>{isHindi ? "आगे बढ़ें" : "Continue"}</button></>}
    {isSpeak && <p className="live-caption" aria-live="polite">{voice.caption}</p>}
    {(error || voice.error) && <p className="language-error" role="alert">{error || voice.error}</p>}
    {isSpeak && ["name","confirm-name"].includes(step) && <button className="field-voice-button" onClick={()=>{voice.cancel();setStep("name-type");}}>{isHindi?"नाम टाइप करें":"Type name instead"}</button>}
    {isSpeak && ["phone","phone-retry","confirm-phone"].includes(step) && <button className="field-voice-button" onClick={()=>{voice.cancel();setStep("phone-type");}}>{isHindi?"फ़ोन नंबर टाइप करें":"Type phone instead"}</button>}
    {isSpeak && ["returning","returning-retry"].includes(step) && <button className="field-voice-button" onClick={()=>{voice.cancel();setStep("medi-type");}}>{isHindi?"मेडी आईडी टाइप करें":"Type Medi ID instead"}</button>}
    {isSpeak && voice.state !== "speaking" && <button className="voice-choice-button" onClick={()=>voice.state === "listening" ? voice.stopListening() : (stepRunRef.current="",voice.setError(""),setVoiceRetries((value)=>({...value})))}>{voice.state === "listening" ? (isHindi?"सुनना बंद करें":"Stop listening") : (isHindi?"🎙 फिर से प्रयास करें":"🎙 Try voice again")}</button>}
    <div className="compact-actions"><button className="secondary-start-button" onClick={()=>{stepRunRef.current="";setStep("question");}}>{isHindi?"वापस":"Back"}</button><button className="secondary-start-button" onClick={onBack}>{isHindi?"शुरुआत":"Start screen"}</button></div>
    <ClearDataButton language={language} onClearData={onClearData} />
  </section></main>;
}

export default PatientIdentification;
