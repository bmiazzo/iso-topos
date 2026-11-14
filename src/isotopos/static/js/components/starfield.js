// Deep-space starfield canvas backdrop for the 3D Earth globe stage

export function initStarfield() {
  const canvas = document.getElementById("starfield-canvas");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");

  function renderStars() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = Math.max(300, Math.floor(rect.width));
    canvas.height = Math.max(300, Math.floor(rect.height));
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);

    const grad = ctx.createRadialGradient(w * 0.5, h * 0.5, w * 0.12, w * 0.5, h * 0.5, w * 0.65);
    grad.addColorStop(0, "rgba(14, 116, 144, 0.16)");
    grad.addColorStop(0.5, "rgba(30, 58, 138, 0.08)");
    grad.addColorStop(1, "rgba(2, 6, 23, 0.0)");
    ctx.fillStyle = grad;
    ctx.fillRect(0, 0, w, h);

    let seed = 1337;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };

    const starCount = 320;
    for (let i = 0; i < starCount; i++) {
      const x = rand() * w;
      const y = rand() * h;
      const r = rand() < 0.85 ? 0.6 + rand() * 0.7 : 1.3 + rand() * 1.1;
      const alpha = 0.25 + rand() * 0.7;
      const tint =
        rand() < 0.3 ? "186, 230, 253" : rand() < 0.6 ? "254, 243, 199" : "241, 245, 249";
      ctx.fillStyle = `rgba(${tint}, ${alpha.toFixed(2)})`;
      ctx.beginPath();
      ctx.arc(x, y, r, 0, Math.PI * 2);
      ctx.fill();
    }
  }

  renderStars();
  window.addEventListener("resize", renderStars);
}
