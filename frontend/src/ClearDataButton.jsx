import { useEffect, useRef, useState } from "react";

// Confirmation gate before wiping session data: a kiosk sits in a public,
// touchable space, so the destructive "clear everything" action needs one
// extra deliberate step. Self-contained (no parent screen needs to change)
// so it drops into every page that already renders <ClearDataButton />.
function ClearDataButton({ onClearData, language = "en" }) {
  const isHindi = language === "hi";
  const [isConfirming, setIsConfirming] = useState(false);
  const triggerRef = useRef(null);
  const dialogRef = useRef(null);

  useEffect(() => {
    if (!isConfirming) return undefined;
    const dialog = dialogRef.current;
    const focusable = () => [...dialog.querySelectorAll("button:not(:disabled)")];
    focusable()[0]?.focus();
    const handleKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setIsConfirming(false);
        return;
      }
      if (event.key !== "Tab") return;
      const items = focusable();
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      triggerRef.current?.focus();
    };
  }, [isConfirming]);

  function confirmClear() {
    setIsConfirming(false);
    onClearData();
  }

  return (
    <>
      <button ref={triggerRef} className="clear-data-button" type="button" onClick={() => setIsConfirming(true)}>
        {isHindi ? "रद्द करें और इस मुलाकात का डेटा मिटाएँ" : "Cancel and clear my data"}
      </button>
      {isConfirming && (
        <div className="clear-confirm-overlay" role="presentation" onClick={() => setIsConfirming(false)}>
          <div
            ref={dialogRef}
            className="clear-confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-label={isHindi ? "इस मुलाकात का डेटा मिटाने की पुष्टि करें" : "Confirm clearing your visit data"}
            onClick={(event) => event.stopPropagation()}
          >
            <p className="clear-confirm-heading">{isHindi ? "यह मुलाकात मिटाकर फिर से शुरू करें?" : "Clear this visit and start over?"}</p>
            <p className="clear-confirm-copy">{isHindi ? "इस मुलाकात का साक्षात्कार, दस्तावेज़ और अलर्ट मिट जाएँगे। आपकी दोबारा उपयोग की जा सकने वाली मेडी आईडी बनी रहेगी।" : "This visit's interview, documents, and alerts will be erased. Your reusable Medi ID registration will remain."}</p>
            <div className="clear-confirm-actions">
              <button className="clear-confirm-no" type="button" onClick={() => setIsConfirming(false)} autoFocus>
                {isHindi ? "नहीं, जारी रखें" : "No, keep going"}
              </button>
              <button className="clear-confirm-yes" type="button" onClick={confirmClear}>
                {isHindi ? "हाँ, मुलाकात मिटाएँ" : "Yes, clear this visit"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ClearDataButton;
