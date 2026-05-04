// Laurion — shared nav script
(function () {
  var toggle  = document.querySelector(".nav-toggle");
  var links   = document.querySelector(".nav-links");
  var overlay = document.querySelector(".nav-overlay");
  if (!toggle) return;

  toggle.addEventListener("click", function () {
    var open = links.classList.toggle("open");
    toggle.classList.toggle("open");
    overlay.classList.toggle("visible");
    document.body.style.overflow = open ? "hidden" : "";
  });

  overlay.addEventListener("click", function () {
    links.classList.remove("open");
    toggle.classList.remove("open");
    overlay.classList.remove("visible");
    document.body.style.overflow = "";
  });

  links.querySelectorAll("a").forEach(function (a) {
    a.addEventListener("click", function () {
      links.classList.remove("open");
      toggle.classList.remove("open");
      overlay.classList.remove("visible");
      document.body.style.overflow = "";
    });
  });
})();
