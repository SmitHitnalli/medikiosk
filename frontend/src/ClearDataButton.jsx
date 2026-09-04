import { useState } from "react";

// Confirmation gate before wiping session data: a kiosk sits in a public,
// touchable space, so the destructive "clear everything" action needs one
// extra deliberate step. Self-contained (no parent screen needs to change)
// so it drops into every page that already renders <ClearDataButton />.
function ClearDataButton({ onClearData }) {
  const [isConfirming, setIsConfirming] = useState(false);

  function confirmClear() {
    setIsConfirming(false);
    onClearData();
  }

  return (
    <>
      <button className="clear-data-button" type="button" onClick={() => setIsConfirming(true)}>
        Cancel and clear my data
      </button>
      {isConfirming && (
        <div className="clear-confirm-overlay" role="presentation" onClick={() => setIsConfirming(false)}>
          <div
            className="clear-confirm-dialog"
            role="alertdialog"
            aria-modal="true"
            aria-label="Confirm clearing your data"
            onClick={(event) => event.stopPropagation()}
          >
            <p className="clear-confirm-heading">Clear all your data and start over?</p>
            <p className="clear-confirm-copy">Everything you've entered so far will be erased. This can't be undone.</p>
            <div className="clear-confirm-actions">
              <button className="clear-confirm-no" type="button" onClick={() => setIsConfirming(false)} autoFocus>
                No, keep going
              </button>
              <button className="clear-confirm-yes" type="button" onClick={confirmClear}>
                Yes, clear everything
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default ClearDataButton;
