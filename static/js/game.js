// M9: round page behaviour. Timer, Spacebar start, Ready to Guess, reveal/hide, timer sound.
(function () {
  const root = document.getElementById("round");
  if (!root) return;

  const phases = root.querySelectorAll(".phase");
  const statement = document.getElementById("statement");
  const placeholder = document.getElementById("statement-placeholder");
  const toggle = document.getElementById("toggle-statement");
  const timerEl = document.getElementById("timer");
  const readyBtn = document.getElementById("ready");
  const guessForm = document.getElementById("guess-form");
  const guessInput = document.getElementById("guess-input");
  const totalSeconds = parseInt(root.dataset.seconds, 10);

  let phase = root.dataset.phase;
  let timerId = null;

  function show(name) {
    phase = name;
    phases.forEach((el) => { el.hidden = el.dataset.show !== name; });
    if (name === "guess" && guessInput) guessInput.focus();
  }

  // FR8: speaker reveals, then hides, the statement
  toggle.addEventListener("click", () => {
    const hidden = statement.hidden;
    statement.hidden = !hidden;
    placeholder.hidden = hidden;
    toggle.textContent = hidden ? "Hide statement" : "Reveal statement";
  });

  function format(s) {
    const m = Math.floor(s / 60);
    return `${m}:${String(s % 60).padStart(2, "0")}`;
  }

  // FR18: short beep using the Web Audio API (no sound file needed)
  function beep() {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      [0, 0.35, 0.7].forEach((t) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = 880;
        gain.gain.setValueAtTime(0.25, ctx.currentTime + t);
        gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + t + 0.3);
        osc.connect(gain).connect(ctx.destination);
        osc.start(ctx.currentTime + t);
        osc.stop(ctx.currentTime + t + 0.3);
      });
    } catch (e) { /* sound is a nice-to-have */ }
  }

  // FR10: countdown, then move to guessing at 0:00
  function startTimer() {
    const endAt = Date.now() + totalSeconds * 1000;
    const tick = () => {
      const left = Math.max(0, Math.round((endAt - Date.now()) / 1000));
      timerEl.textContent = format(left);
      if (left === 0) {
        clearInterval(timerId);
        beep();
        show("guess");
      }
    };
    tick();
    timerId = setInterval(tick, 250);
  }

  // FR9: Spacebar starts the round, only from the privacy screen with the statement hidden
  document.addEventListener("keydown", (e) => {
    if (e.code !== "Space" || phase !== "privacy") return;
    if (["INPUT", "TEXTAREA", "BUTTON"].includes(document.activeElement.tagName)) {
      document.activeElement.blur();
    }
    e.preventDefault();
    if (!statement.hidden) {
      document.getElementById("space-hint").classList.add("flash");
      return;
    }
    show("questioning");
    startTimer();
  });

  // FR11: guess early
  readyBtn.addEventListener("click", () => {
    clearInterval(timerId);
    show("guess");
  });

  // FR12: confirm before submitting, in a themed dialog
  const dialog = document.getElementById("confirm-dialog");
  const confirmWord = document.getElementById("confirm-word");
  guessForm.addEventListener("submit", (e) => {
    const g = guessInput.value.trim().toUpperCase();
    if (g !== "T" && g !== "L") return; // let the server show the error
    e.preventDefault();
    const isTruth = g === "T";
    confirmWord.textContent = isTruth ? "TRUTH" : "LIE";
    confirmWord.className = "confirm-word " + (isTruth ? "truth" : "lie");
    dialog.showModal();
    document.getElementById("confirm-ok").focus();
  });
  document.getElementById("confirm-ok").addEventListener("click", () => guessForm.submit());
  document.getElementById("confirm-cancel").addEventListener("click", () => {
    dialog.close();
    guessInput.focus();
  });

  show(phase);
})();
