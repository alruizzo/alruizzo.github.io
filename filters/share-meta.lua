--[[
Link-preview metadata that Quarto does not emit on its own.

Quarto's `open-graph` and `twitter-card` options already write og:title, og:description,
og:image (+ width, height, alt), og:site_name, og:locale and the twitter:* tags. This filter adds
the page-specific pieces messaging apps and social platforms also rely on:

  * og:url and <link rel="canonical">: the page's public address, built from `website.site-url`
    in _quarto.yml (read here, so the URL has a single source) and the page's output path;
  * og:type: `website`, or the page's `share-type` (e.g. `profile`, with `profile:*` tags);
  * og:image:type: from the share image's file extension;
  * robots noindex (and no canonical) for pages marked `share-noindex: true`, such as the 404.

scripts/check_site.py verifies the rendered result for every page.
]]

local function read_site_url()
  local path = pandoc.path.join({ quarto.project.directory, "_quarto.yml" })
  local fh = io.open(path, "r")
  if not fh then error("share-meta.lua: cannot read " .. path) end
  local text = fh:read("a")
  fh:close()
  local meta = pandoc.read("---\n" .. text .. "\n---\n", "markdown").meta
  local site = meta.website and meta.website["site-url"]
  if not site then error("share-meta.lua: website.site-url missing in _quarto.yml") end
  return (pandoc.utils.stringify(site):gsub("/+$", ""))
end

local function attr(s)
  return (s:gsub("&", "&amp;"):gsub('"', "&quot;"):gsub("<", "&lt;"))
end

local IMAGE_TYPES = { png = "image/png", jpg = "image/jpeg", jpeg = "image/jpeg", webp = "image/webp" }

function Meta(meta)
  if not quarto.doc.is_format("html") then return nil end
  local site = read_site_url()
  local rel = pandoc.path.make_relative(quarto.doc.input_file, quarto.project.directory)
  rel = rel:gsub("%.qmd$", ".html"):gsub("\\", "/")
  local url = site .. "/" .. (rel == "index.html" and "" or rel)

  local tags = {}
  local function add(s) tags[#tags + 1] = s end

  if meta["share-noindex"] then
    add('<meta name="robots" content="noindex">')
  else
    add('<link rel="canonical" href="' .. attr(url) .. '">')
    add('<meta property="og:url" content="' .. attr(url) .. '">')
  end

  local share_type = meta["share-type"] and pandoc.utils.stringify(meta["share-type"]) or "website"
  add('<meta property="og:type" content="' .. attr(share_type) .. '">')
  if share_type == "profile" and meta["share-profile"] then
    for _, key in ipairs({ "first_name", "last_name" }) do
      local v = meta["share-profile"][key]
      if v then add('<meta property="profile:' .. key .. '" content="' .. attr(pandoc.utils.stringify(v)) .. '">') end
    end
  end

  if meta.image then
    local ext = pandoc.utils.stringify(meta.image):match("%.([%w]+)$")
    local mime = ext and IMAGE_TYPES[ext:lower()]
    if mime then add('<meta property="og:image:type" content="' .. mime .. '">') end
  end

  quarto.doc.include_text("in-header", table.concat(tags, "\n"))
  return nil
end
