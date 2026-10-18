// Material stores consent and reloads after a choice; no badge request precedes it.
function loadApizrFeedbackBadge() {
  const block = document.querySelector("[data-apizr-producthunt]");
  if (!block || typeof __md_get !== "function") return;
  const consent = __md_get("__consent");
  if (!consent || consent.producthunt !== true) return;

  for (const image of block.querySelectorAll("[data-apizr-badge-src]")) {
    if (!image.hasAttribute("src")) image.src = image.dataset.apizrBadgeSrc;
    image.hidden = false;
  }
  block.querySelector(".apizr-home-feedback__placeholder").hidden = true;
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", loadApizrFeedbackBadge, {once: true});
} else {
  loadApizrFeedbackBadge();
}
