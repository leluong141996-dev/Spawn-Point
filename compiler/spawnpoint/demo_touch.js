// Touch controls for the Spawn Point demo games (phones and tablets).
// Each game page sets window.SP_TOUCH = {pad: "lr" | "dpad" | null, buttons: [[label, code], ...], tap: "hint"}.
// Buttons send the same keyboard events a keyboard would, straight to Godot's canvas, so the games need no
// changes; taps on the canvas itself reach Godot as mouse clicks (aiming, upgrade cards).
(function () {
  var cfg = window.SP_TOUCH || {};
  var coarse = window.matchMedia && matchMedia("(pointer: coarse)").matches;
  var forced = location.search.indexOf("touch") >= 0;  // ?touch shows the controls on a desktop (testing)
  if (!(coarse || forced || "ontouchstart" in window) || location.search.indexOf("shot") >= 0) return;

  var KEYS = {Space: " ", ShiftLeft: "Shift", KeyX: "x", KeyR: "r", KeyE: "e", Digit1: "1", Digit2: "2", Digit3: "3", KeyP: "p", KeyN: "n", KeyM: "m",
              ArrowLeft: "ArrowLeft",
              ArrowRight: "ArrowRight", ArrowUp: "ArrowUp", ArrowDown: "ArrowDown"};
  var held = {};
  function send(code, on) {
    if (!!held[code] === on) return;
    held[code] = on;
    var canvas = document.getElementById("canvas");
    if (!canvas) return;
    canvas.dispatchEvent(new KeyboardEvent(on ? "keydown" : "keyup",
      {code: code, key: KEYS[code] || code, bubbles: true, cancelable: true}));
  }

  var css = document.createElement("style");
  css.textContent =
    ".sp-touch{position:fixed;z-index:20;display:flex;gap:12px;user-select:none;-webkit-user-select:none;touch-action:none}" +
    ".sp-btn{width:64px;height:64px;border-radius:50%;background:rgba(255,255,255,.16);border:2px solid rgba(255,255,255,.45);" +
    "color:#fff;font:700 14px/60px ui-monospace,Menlo,monospace;text-align:center;touch-action:none}" +
    ".sp-btn.big{width:84px;height:84px;line-height:80px;font-size:16px}.sp-btn.on{background:rgba(255,236,39,.45)}" +
    ".sp-pad{width:136px;height:136px;border-radius:50%;background:rgba(255,255,255,.12);border:2px solid rgba(255,255,255,.4);" +
    "position:relative;touch-action:none}.sp-knob{position:absolute;left:43px;top:43px;width:46px;height:46px;border-radius:50%;" +
    "background:rgba(255,255,255,.5)}#sp-rotate{position:fixed;inset:0;z-index:30;display:none;align-items:center;" +
    "justify-content:center;background:#14121c;color:#fff;font:600 18px system-ui;text-align:center;padding:24px}" +
    "@media (orientation:portrait){#sp-rotate{display:flex}}#sp-hint{position:fixed;left:50%;top:40%;z-index:20;" +
    "transform:translateX(-50%);color:#fff;background:rgba(0,0,0,.55);padding:8px 14px;border-radius:8px;" +
    "font:600 14px system-ui;pointer-events:none;transition:opacity 1s}#sp-bar span{display:none}";  // keyboard help hides
  document.head.appendChild(css);

  function button(label, code, big) {
    var b = document.createElement("div");
    b.className = "sp-btn" + (big ? " big" : "");
    b.textContent = label;
    b.addEventListener("pointerdown", function (e) {
      e.preventDefault();
      b.setPointerCapture(e.pointerId);
      b.classList.add("on");
      send(code, true);
    });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (t) {
      b.addEventListener(t, function () { b.classList.remove("on"); send(code, false); });
    });
    return b;
  }

  function dpad() {
    var pad = document.createElement("div"), knob = document.createElement("div");
    pad.className = "sp-pad";
    knob.className = "sp-knob";
    pad.appendChild(knob);
    function update(e) {
      var r = pad.getBoundingClientRect();
      var dx = (e.clientX - r.left - r.width / 2) / (r.width / 2);
      var dy = (e.clientY - r.top - r.height / 2) / (r.height / 2);
      var len = Math.sqrt(dx * dx + dy * dy) || 1, k = Math.min(1, len) / len;
      knob.style.transform = "translate(" + dx * k * 45 + "px," + dy * k * 45 + "px)";
      send("ArrowLeft", dx < -0.35); send("ArrowRight", dx > 0.35);
      send("ArrowUp", dy < -0.35); send("ArrowDown", dy > 0.35);
    }
    function release() {
      knob.style.transform = "";
      ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].forEach(function (c) { send(c, false); });
    }
    pad.addEventListener("pointerdown", function (e) { e.preventDefault(); pad.setPointerCapture(e.pointerId); update(e); });
    pad.addEventListener("pointermove", function (e) { if (pad.hasPointerCapture(e.pointerId)) update(e); });
    ["pointerup", "pointercancel", "lostpointercapture"].forEach(function (t) { pad.addEventListener(t, release); });
    return pad;
  }

  addEventListener("DOMContentLoaded", function () {
    var rotate = document.createElement("div");
    rotate.id = "sp-rotate";
    rotate.textContent = "Turn your phone sideways to play ↻";
    document.body.appendChild(rotate);

    var left = document.createElement("div");
    left.className = "sp-touch";
    left.style.cssText = "left:18px;bottom:64px";
    if (cfg.pad === "lr") {
      left.appendChild(button("◀", "ArrowLeft", true));
      left.appendChild(button("▶", "ArrowRight", true));
    } else if (cfg.pad === "dpad") {
      left.appendChild(dpad());
    }
    document.body.appendChild(left);

    var right = document.createElement("div");
    right.className = "sp-touch";
    right.style.cssText = "right:18px;bottom:64px;flex-direction:row-reverse;align-items:flex-end";
    (cfg.buttons || []).forEach(function (b, i) { right.appendChild(button(b[0], b[1], i === 0)); });
    document.body.appendChild(right);

    var restart = document.createElement("div");
    restart.className = "sp-touch";
    restart.style.cssText = "right:14px;top:48px";
    var r = button("↻", "KeyR");
    r.style.cssText = "width:44px;height:44px;line-height:40px;font-size:20px";
    restart.appendChild(r);
    document.body.appendChild(restart);

    if (cfg.tap) {
      var hint = document.createElement("div");
      hint.id = "sp-hint";
      hint.textContent = cfg.tap;
      document.body.appendChild(hint);
      setTimeout(function () { hint.style.opacity = "0"; }, 3500);
    }
  });
})();
