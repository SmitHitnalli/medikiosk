function ClearDataButton({ onClearData }) {
  return (
    <button className="clear-data-button" type="button" onClick={onClearData}>
      Cancel and clear my data
    </button>
  );
}

export default ClearDataButton;
