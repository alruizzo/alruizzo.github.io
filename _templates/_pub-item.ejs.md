<%
// One publication entry. Shared by pubs.ejs (full) and pubs-compact.ejs.
// Inputs: item (a record from data/publications.yml), metadataAttrs (Quarto helper), compact (bool).
// Interface strings: English defaults, overridden per language by scripts/build_site.py (T).
const S = Object.assign({
  authors: "authors", open_access: "Open access", in_spanish: "In Spanish", doi_for: "DOI for",
  preprint: "Preprint", preprint_of: "Preprint of", data_code: "Data and code", data_code_for: "Open data and code for",
  cite: "Cite",
  types: { preprint: "Preprint, not peer reviewed", abstract: "Conference abstract", thesis: "Thesis", chapter: "Book chapter", scicomm: "Science communication" },
  themes: { attention: "Visual attention", networks: "Brain networks", decline: "Cognitive decline and dementia", lifestyle: "Lifestyle and interventions", clinical: "Clinical neuroscience", data: "Data science" },
}, (typeof T !== "undefined" && T) || {});
const THEME_SLUG = Object.fromEntries(Object.entries(S.themes).map(([slug, name]) => [name, slug]));
const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
const isMe = (a) => /^Ruiz(?:[- ]Rizzo)?\s+A/.test(a);
const authors = item.authors || [];
const fmtAuthors = () => {
  if (!authors.length) return "";
  const mark = (a) => isMe(a) ? `<strong>${esc(a)}</strong>` : esc(a);
  if (authors.length <= 10) return authors.map(mark).join(", ");
  // Long consortium lists: first six, her position, last author, and the total.
  const me = authors.findIndex(isMe);
  const head = authors.slice(0, 6).map(mark);
  const tail = [];
  if (me >= 6 && me < authors.length - 1) tail.push("…", mark(authors[me]));
  tail.push("…", mark(authors[authors.length - 1]));
  return head.concat(tail).join(", ") + ` <span class="rr-num">(${authors.length} ${S.authors})</span>`;
};
const apaName = (a) => {
  const parts = a.split(" ");
  if (parts.length < 2) return a;
  const ini = parts.pop();
  return `${parts.join(" ")}, ${ini.split("").map((c) => c + ".").join(" ")}`;
};
const apa = () => {
  let names = authors.map(apaName);
  if (names.length > 20) names = names.slice(0, 19).concat(["…", names[names.length - 1]]);
  const who = names.length > 1 ? names.slice(0, -1).join(", ") + ", & " + names[names.length - 1] : (names[0] || "");
  let s = `${esc(who)} (${item.year}). ${esc(item.title)}. <em>${esc(item.venue || "")}</em>`;
  if (item.volume) s += `, <em>${esc(item.volume)}</em>`;
  if (item.issue && !/^S|Part/i.test(item.issue)) s += `(${esc(item.issue)})`;
  if (item.pages) s += `, ${esc(item.pages)}`;
  s += ".";
  if (item.doi) s += ` https://doi.org/${esc(item.doi)}`;
  else if (item.url) s += ` ${esc(item.url)}`;
  return s;
};
const href = item.doi ? `https://doi.org/${item.doi}` : (item.url || "");
const lang = item.language ? ` lang="${esc(item.language)}"` : "";
const venueBits = [];
if (item.volume) venueBits.push(esc(item.volume) + (item.issue ? `(${esc(item.issue)})` : ""));
if (item.pages) venueBits.push(esc(item.pages));
const TYPE_LABEL = S.types;
%>
<article class="rr-pub" id="pub-<%- item.id %>" <%= metadataAttrs(item) %>>
<div class="rr-year"><%- item.year %></div>
<div class="rr-pub-body">
<h3 class="rr-pub-title listing-title"<%= lang %>><% if (href) { %><a href="<%= href %>"><%- item.title %></a><% } else { %><%- item.title %><% } %></h3>
<% if (authors.length) { %><p class="rr-pub-authors listing-authors"><%= fmtAuthors() %></p><% } %>
<% if (item.venue) { %><p class="rr-pub-venue listing-venue"><em><%- item.venue %></em><% if (venueBits.length) { %>, <span class="rr-num"><%= venueBits.join(", ") %></span><% } %></p><% } %>
<% if (!compact && item.note) { %><p class="rr-pub-note"><%- item.note %></p><% } %>
<% if (!compact) { %>
<div class="rr-pub-meta">
<% for (const c of (item.categories || [])) { %><span class="rr-chip rr-theme <%- THEME_SLUG[c] || '' %>"><%- c %></span><% } %>
<% if (TYPE_LABEL[item.type]) { %><span class="rr-badge"><%- TYPE_LABEL[item.type] %></span><% } %>
<% if (item.open_access) { %><span class="rr-badge"><%- S.open_access %></span><% } %>
<% if (item.language === "es") { %><span class="rr-badge"><%- S.in_spanish %></span><% } %>
<% if (item.doi) { %><a href="https://doi.org/<%= item.doi %>" aria-label="<%- S.doi_for %> <%- item.title %>">DOI</a><% } %>
<% if (item.preprint) { %><a href="https://doi.org/<%= item.preprint %>" aria-label="<%- S.preprint_of %> <%- item.title %>"><%- S.preprint %></a><% } %>
<% (item.data || []).forEach((d, i) => { %><a href="<%= d %>" aria-label="<%- S.data_code_for %> <%- item.title %>"><%- S.data_code %><%- (item.data.length > 1) ? " " + (i + 1) : "" %></a><% }) %>
</div>
<details><summary><%- S.cite %></summary><p><%= apa() %></p></details>
<% } %>
</div>
</article>
