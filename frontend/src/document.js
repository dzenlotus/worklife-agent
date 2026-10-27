// CVs use headings, paragraphs and lists. Keep all other content as literal text.
export function documentBlocks(markdown = "") {
  const blocks = [];
  for (const line of String(markdown).replaceAll("\r\n", "\n").split("\n")) {
    if (!line.trim()) { blocks.push({ type: "break" }); continue; }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) { blocks.push({ type: "heading", level: heading[1].length, text: heading[2] }); continue; }
    const item = line.match(/^\s*(?:[-*+] |\d+\. )(.+)$/);
    const type = item ? "list" : "paragraph", text = item ? item[1] : line;
    const previous = blocks.at(-1);
    if (previous?.type === type) {
      if (item) previous.items.push(text);
      else previous.text += " " + text;
    } else blocks.push(item ? { type, items: [text] } : { type, text });
  }
  return blocks.filter((block) => block.type !== "break");
}
