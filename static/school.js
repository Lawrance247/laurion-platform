// Laurion — nav toggle script
document.addEventListener("DOMContentLoaded", function () {
  var toggle  = document.querySelector(".nav-toggle");
  var links   = document.querySelector(".nav-links");
  var overlay = document.querySelector(".nav-overlay");
  var closeBtn = document.querySelector(".nav-close");
  if (!toggle || !links || !overlay) return;

  function openNav() {
    links.classList.add("open");
    toggle.classList.add("open");
    overlay.classList.add("visible");
    document.body.style.overflow    = "hidden";
    document.body.style.touchAction = "none";
  }

  function closeNav() {
    links.classList.remove("open");
    toggle.classList.remove("open");
    overlay.classList.remove("visible");
    document.body.style.overflow    = "";
    document.body.style.touchAction = "";
  }

  toggle.addEventListener("click", function (e) {
    e.stopPropagation();
    links.classList.contains("open") ? closeNav() : openNav();
  });

  overlay.addEventListener("click", closeNav);

  if (closeBtn) closeBtn.addEventListener("click", closeNav);

  links.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", closeNav);
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeNav();
  });
});
