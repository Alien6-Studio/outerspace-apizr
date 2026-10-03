// Keep the cover local and load YouTube only after an explicit play action.
document.addEventListener("click", (event) => {
  const cover = event.target.closest("[data-apizr-video]");
  if (!cover || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

  const id = cover.dataset.apizrVideo;
  if (!/^[A-Za-z0-9_-]{11}$/.test(id)) return;

  event.preventDefault();
  const player = document.createElement("iframe");
  player.src = `https://www.youtube-nocookie.com/embed/${id}?autoplay=1&playsinline=1&rel=0`;
  player.title = "Apizr demonstration: generate REST and MCP from a Python notebook";
  player.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
  player.allowFullscreen = true;
  player.referrerPolicy = "strict-origin-when-cross-origin";
  cover.replaceWith(player);
  player.focus();
});
