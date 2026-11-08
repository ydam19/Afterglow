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

  /* ---------- 기록 작성: 노을 계산용 위치 ---------- */
  const locBtn = document.querySelector("[data-locate]");
  if (locBtn) {
    const form = locBtn.closest("form");
    const status = document.querySelector("[data-locate-status]");
    try {
      form.elements.tz.value = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    } catch (_) { /* 시간대 못 읽으면 서버가 서울로 처리 */ }

    if (!("geolocation" in navigator)) {
      locBtn.hidden = true;
    } else {
      locBtn.addEventListener("click", () => {
        locBtn.disabled = true;
        status.textContent = "위치를 찾는 중…";
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const lat = pos.coords.latitude.toFixed(2);
            const lon = pos.coords.longitude.toFixed(2);
            form.elements.lat.value = lat;
            form.elements.lon.value = lon;
            status.textContent = "지금 위치의 노을 시각으로 기록돼요";
            status.classList.add("ok");
            locBtn.textContent = "📍 위치 맞춤 완료";
            // 어느 시인지 미리 보여줌 (실패해도 기록에는 지장 없음)
            fetch("/place?lat=" + lat + "&lon=" + lon, { credentials: "same-origin" })
              .then((r) => (r.ok ? r.json() : null))
              .then((d) => {
                if (d && d.place) {
                  status.textContent = d.place + "의 노을 시각으로 기록돼요";
                  locBtn.textContent = "📍 " + d.place;
                }
              })
              .catch(() => {});
          },
          () => {
            locBtn.disabled = false;
            status.textContent = "위치를 가져오지 못했어요. 서울 기준으로 계산할게요";
          },
          { enableHighAccuracy: false, timeout: 10000, maximumAge: 600000 }
        );
      });
    }
  }

  /* ---------- 기록하기: 저무는 빛 연출과 저장을 동시에 ---------- */
  const sunsetForm = document.querySelector("[data-sunset-submit]");
  const scene = document.querySelector(".dusk-scene");
  if (sunsetForm && scene && window.fetch && window.FormData) {
    const live = document.querySelector("[data-sunset-live]");
    const submitBtn = sunsetForm.querySelector("button[type=submit]");
    const frame = scene.querySelector(".ds-frame");
    const img = scene.querySelector(".ds-photo img");
    const noteEl = scene.querySelector(".ds-note");
    const skipBtn = scene.querySelector(".ds-skip");
    const dur = reduce ? 1600 : 7600; // CSS --dur 과 맞춤
    let photoUrl = null;

    const showError = (msg) => {
      let box = document.querySelector(".flash");
      if (!box) {
        box = document.createElement("div");
        box.className = "flash";
        document.querySelector("main.container").before(box);
      }
      box.innerHTML = "";
      const p = document.createElement("p");
      p.textContent = msg;
      box.appendChild(p);
      box.scrollIntoView({ behavior: "smooth", block: "center" });
    };

    // 방금 고른 사진과 쓴 한 줄을 연출에 채움
    const fillScene = () => {
      const file = sunsetForm.elements.image && sunsetForm.elements.image.files[0];
      if (photoUrl) URL.revokeObjectURL(photoUrl);
      photoUrl = file ? URL.createObjectURL(file) : null;
      if (photoUrl) img.src = photoUrl; else img.removeAttribute("src");
      frame.classList.toggle("no-photo", !photoUrl);
      const note = (sunsetForm.elements.note.value || "").trim();
      const moodEl = sunsetForm.querySelector("input[name=mood]:checked");
      const moodLabel = moodEl ? moodEl.nextElementSibling.textContent.trim() : "";
      noteEl.textContent = note || moodLabel;
    };

    const resetScene = () => {
      scene.classList.add("leave");
      setTimeout(() => {
        scene.hidden = true;
        scene.classList.remove("play", "leave", "waiting", "saved");
      }, 700);
    };

    sunsetForm.addEventListener("submit", (ev) => {
      ev.preventDefault();
      if (submitBtn.disabled) return;
      submitBtn.disabled = true;

      fillScene();
      scene.hidden = false;
      void scene.offsetWidth; // 다음 프레임에 전환 시작
      scene.classList.add("play");
      if (live) live.textContent = "기록을 저장하는 중이에요";

      let skip;
      const skipped = new Promise((r) => (skip = r));
      const animDone = Promise.race([new Promise((r) => setTimeout(r, dur)), skipped]);
      const saved = fetch(sunsetForm.action || location.href, {
        method: "POST",
        body: new FormData(sunsetForm),
        headers: { "X-Afterglow-Async": "1" },
        credentials: "same-origin",
        redirect: "manual",
      }).then(async (res) => {
        if (res.type === "opaqueredirect") return { ok: false, relogin: true };
        try { return await res.json(); }
        catch (_) { return { ok: false, error: "기록을 저장하지 못했어요. 잠시 후 다시 시도해 주세요." }; }
      }).catch(() => ({ ok: false, error: "인터넷 연결을 확인해 주세요." }));

      animDone.then(() => scene.classList.add("waiting"));

      saved.then((result) => {
        if (result.relogin) { location.href = "/login"; return; }
        if (result.ok) {
          // 저장이 끝났으면 기다리기 싫은 사람은 넘길 수 있게
          scene.classList.add("saved");
          skipBtn.tabIndex = 0;
          skipBtn.onclick = skip;
          scene.addEventListener("click", skip, { once: true });
          animDone.then(() => {
            scene.classList.add("depart");
            setTimeout(() => { location.href = result.redirect || "/"; }, reduce ? 0 : 800);
          });
          return;
        }
        resetScene();
        submitBtn.disabled = false;
        if (live) live.textContent = result.error;
        showError(result.error || "기록을 저장하지 못했어요.");
      });
    });
  }

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
