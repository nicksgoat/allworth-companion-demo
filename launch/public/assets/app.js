// Allworth Companion — launch page behavior.
// Tiny hash router (#/ pitch, #/updates) + renders content.js + lightbox + reveal.
(function () {
  "use strict";

  var C = window.ALW_CONTENT || {};
  var $ = function (sel, root) {
    return (root || document).querySelector(sel);
  };
  var el = function (tag, cls, html) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  var esc = function (s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  };

  // ---- Meta (hero pill + footer) ----
  function renderMeta() {
    var m = C.meta || {};
    var v = $("#hero-version");
    if (v)
      v.textContent =
        "iOS · " + (m.channel || "TestFlight") + (m.build ? " · Build " + m.build : "");
    var model = $("#hero-model");
    if (model && m.model) model.textContent = m.model;
    var fv = $("#footer-version");
    if (fv) fv.textContent = "Allworth Companion · v" + (m.version || "1.0.0");
  }

  // ---- Features ----
  function renderFeatures() {
    var mount = $("#features");
    if (!mount || !C.features) return;
    C.features.forEach(function (f) {
      var card = el("div", "card feature reveal");
      card.appendChild(el("div", "feature__tag", esc(f.tag)));
      card.appendChild(el("h3", null, esc(f.title)));
      card.appendChild(el("p", null, esc(f.body)));
      mount.appendChild(card);
    });
  }

  // ---- Screens (device frames) ----
  function renderScreens() {
    var mount = $("#screens");
    if (!mount || !C.screenshots) return;
    C.screenshots.forEach(function (s) {
      var shot = el("div", "shot reveal");
      var device = el("div", "device");
      var src = "assets/screenshots/" + s.file;
      var img = el("img");
      img.alt = s.caption || "";
      img.loading = "lazy";
      img.decoding = "async";
      img.src = src;
      // If the capture isn't in place yet, show a tasteful empty frame.
      img.onerror = function () {
        device.classList.add("device--empty");
        device.innerHTML = "<span>Screenshot coming</span>";
      };
      device.appendChild(img);
      device.addEventListener("click", function () {
        if (!device.classList.contains("device--empty")) openLightbox(src, s.caption);
      });
      shot.appendChild(device);
      shot.appendChild(el("div", "shot__caption", esc(s.caption)));
      if (s.sub) shot.appendChild(el("div", "shot__sub", esc(s.sub)));
      mount.appendChild(shot);
    });
  }

  // ---- Changelog ----
  function renderChangelog() {
    var mount = $("#changelog");
    if (!mount || !C.releases) return;
    C.releases.forEach(function (r) {
      var card = el("div", "card release reveal");
      var head = el("div", "release__head");
      var label = typeof r.build === "number" ? "Build " + r.build : esc(r.build);
      head.appendChild(el("span", "release__build", label));
      if (r.channel) head.appendChild(el("span", "release__badge", esc(r.channel)));
      if (r.date) head.appendChild(el("span", "release__date", esc(r.date)));
      card.appendChild(head);
      if (r.title) card.appendChild(el("div", "release__title", esc(r.title)));
      if (r.notes && r.notes.length) {
        var ul = el("ul");
        r.notes.forEach(function (n) {
          ul.appendChild(el("li", null, esc(n)));
        });
        card.appendChild(ul);
      }
      mount.appendChild(card);
    });
  }

  // ---- Lightbox ----
  var lb = $("#lightbox"),
    lbImg = $("#lightbox-img");
  function openLightbox(src, alt) {
    if (!lb) return;
    lbImg.src = src;
    lbImg.alt = alt || "";
    lb.classList.add("open");
  }
  function closeLightbox() {
    if (lb) lb.classList.remove("open");
  }
  if (lb) {
    $("#lightbox-close").addEventListener("click", closeLightbox);
    lb.addEventListener("click", function (e) {
      if (e.target === lb) closeLightbox();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeLightbox();
    });
  }

  // ---- Reveal on scroll ----
  function observeReveals() {
    var items = document.querySelectorAll(".reveal:not(.in)");
    if (!("IntersectionObserver" in window)) {
      items.forEach(function (n) {
        n.classList.add("in");
      });
      return;
    }
    var io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            en.target.classList.add("in");
            io.unobserve(en.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.08 }
    );
    items.forEach(function (n) {
      io.observe(n);
    });
  }

  // ---- Router ----
  var TABS = ["pitch", "updates"];
  function currentView() {
    var h = (location.hash || "").replace(/^#\/?/, "");
    return TABS.indexOf(h) !== -1 ? h : "pitch";
  }
  function route() {
    var view = currentView();
    document.querySelectorAll("[data-view]").forEach(function (v) {
      v.classList.toggle("active", v.getAttribute("data-view") === view);
    });
    document.querySelectorAll(".tab").forEach(function (t) {
      t.classList.toggle("active", t.getAttribute("data-tab") === view);
    });
    window.scrollTo(0, 0);
    observeReveals();
  }
  document.querySelectorAll(".tab").forEach(function (t) {
    t.addEventListener("click", function () {
      location.hash = "/" + t.getAttribute("data-tab");
    });
  });
  window.addEventListener("hashchange", route);

  // ---- Init ----
  renderMeta();
  renderFeatures();
  renderScreens();
  renderChangelog();
  route();
})();
