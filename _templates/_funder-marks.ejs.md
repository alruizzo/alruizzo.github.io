<%
// Logo tiles for a list of funders (from data/generated/*.yml). Logos sit on a white tile in both
// themes so official colors are never altered; funders without a logo render as a wordmark.
%>
<ul class="rr-funder-marks<%= small ? ' is-small' : '' %>" aria-label="<%- (typeof label !== "undefined" && label) || "Funded by" %>">
<% for (const f of funders) { %>
<li><% if (f.logo) { %><span class="rr-logo-tile<%= f.logo_kind === 'eu-emblem' ? ' is-eu-emblem' : '' %><%= f.logo_caption ? ' has-caption' : '' %>"><img src="<%= f.logo %>" alt="<%- f.logo_alt %>" loading="lazy" decoding="async"><% if (f.logo_caption) { %><span class="rr-logo-caption"><%- f.logo_caption %></span><% } %></span><% } else { %><span class="rr-wordmark"><%- f.name %></span><% } %></li>
<% } %>
</ul>
