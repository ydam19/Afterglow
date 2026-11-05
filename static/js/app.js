/* Afterglow — 입체감을 위한 미세 인터랙션
   1) 스크롤 등장(fade-up, stagger)  2) 마우스 3D 틸트  3) 배경 노을 패럴럭스 */

(function () {
  "use strict";
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- 1) 스크롤 등장 ---------- */
  const revealTargets = document.querySelectorAll(".polaroid, .entry-form, .detail, .calendar, .empty");
  revealTargets.forEach((el, i) => {
    el.classList.add("reveal");
    el.style.setProperty("--d", (i % 12) * 55 + "ms");
  });

  if (reduce || !("IntersectionObserver" in window)) {
    revealTargets.forEach((el) => el.classList.add("in"));
  } else {
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add("in");
            io.unobserve(e.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -8% 0px" }
    );
    revealTargets.forEach((el) => io.observe(el));
  }

  /* ---------- 2) 마우스 3D 틸트 ---------- */
  if (!reduce && window.matchMedia("(hover: hover)").matches) {
    const tiltEls = document.querySelectorAll(".polaroid, .detail");
    const MAX = 7; // deg
    tiltEls.forEach((el) => {
      let raf = null;
      el.classList.add("tilt");
      el.addEventListener("pointermove", (ev) => {
        const r = el.getBoundingClientRect();
        const px = (ev.clientX - r.left) / r.width - 0.5;
        const py = (ev.clientY - r.top) / r.height - 0.5;
        if (raf) cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          el.style.setProperty("--rx", (-py * MAX).toFixed(2) + "deg");
          el.style.setProperty("--ry", (px * MAX).toFixed(2) + "deg");
          // 빛 반사 하이라이트 위치
          el.style.setProperty("--mx", (px * 100 + 50).toFixed(1) + "%");
          el.style.setProperty("--my", (py * 100 + 50).toFixed(1) + "%");
        });
      });
      el.addEventListener("pointerleave", () => {
        if (raf) cancelAnimationFrame(raf);
        el.style.setProperty("--rx", "0deg");
        el.style.setProperty("--ry", "0deg");
      });
    });
  }

  /* ---------- 파일 선택: 선택한 파일명 표시 ---------- */
  document.querySelectorAll(".file-field").forEach((wrap) => {
    const input = wrap.querySelector('input[type="file"]');
    const nameEl = wrap.querySelector(".file-name");
    if (!input || !nameEl) return;
    const empty = nameEl.textContent;
    input.addEventListener("change", () => {
      if (input.files && input.files.length) {
        nameEl.textContent = input.files[0].name;
        nameEl.classList.add("has");
      } else {
        nameEl.textContent = empty;
        nameEl.classList.remove("has");
      }
    });
  });

  /* ---------- 3) 배경 노을 패럴럭스 ---------- */
  if (!reduce && window.matchMedia("(hover: hover)").matches) {
    let raf = null;
    window.addEventListener("pointermove", (ev) => {
      const x = ev.clientX / window.innerWidth - 0.5;
      const y = ev.clientY / window.innerHeight - 0.5;
      if (raf) cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        document.body.style.setProperty("--bgx", (x * 18).toFixed(1) + "px");
        document.body.style.setProperty("--bgy", (y * 18).toFixed(1) + "px");
      });
    });
  }
})();
