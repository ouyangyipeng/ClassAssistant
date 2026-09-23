"use strict";

const previews = {
  classroom: {
    src: "assets/classroom.png",
    alt: "ClassFox 实际课堂界面：左侧保存二叉树遍历原文，右侧显示课堂助手的回答",
  },
  notes: {
    src: "assets/notes.png",
    alt: "ClassFox 实际笔记界面：二叉树遍历课堂的 Markdown 笔记与原文分开保存",
  },
};
const tabs = Array.from(document.querySelectorAll("[data-preview]"));
const preview = document.querySelector("#preview-image");
const panel = document.querySelector("#product-preview");

function selectPreview(tab) {
  const item = previews[tab.dataset.preview];
  if (!item || !preview || !panel) return;
  for (const candidate of tabs) {
    const selected = candidate === tab;
    candidate.setAttribute("aria-selected", String(selected));
    candidate.tabIndex = selected ? 0 : -1;
  }
  preview.src = item.src;
  preview.alt = item.alt;
  panel.setAttribute("aria-labelledby", tab.id);
}

for (const [index, tab] of tabs.entries()) {
  tab.addEventListener("click", () => selectPreview(tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft")
      next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next === undefined) return;
    event.preventDefault();
    tabs[next].focus();
    selectPreview(tabs[next]);
  });
}
document.body.classList.add("has-js");
