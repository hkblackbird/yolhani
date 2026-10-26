// Site içi arama: ara.json'u ilk kullanımda yükler.
// Üst menüdeki kutu açılır liste gösterir; ana sayfadaki kutu sonuçları tablo olarak listeler.
(() => {
  const root = document.currentScript.dataset.root || "";
  const norm = s => (s || "").toLocaleLowerCase("tr").replace(/ı/g, "i").normalize("NFD").replace(/[̀-ͯ]/g, "");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  let idx, loading;
  const load = () => loading ||= fetch(root + "ara.json").then(r => r.json()).then(d => {
    const low = s => (s || "").toLocaleLowerCase("tr");
    for (const c of d.c) { c.h = norm(c[1]); c.r = low(c[1]); }
    for (const p of d.p) {
      p.n = norm(p[0]); p.i = norm(p[2]);
      p.h = " " + p.n + " " + d.c[p[1]].h + " " + p.i + " " + norm(d.t[p[3]]);
      p.r = " " + low(p[0]) + " " + d.c[p[1]].r + " " + low(p[2]) + " " + low(d.t[p[3]]);
    }
    return idx = d;
  });

  // Sözcük başında eşleşme aranır; Türkçe harfleri birebir tutan ve ilçe/il adıyla tam eşleşen sonuçlar öne çıkar.
  const wordHas = (h, t) => h.includes(" " + t) || h.includes("(" + t) || h.includes("-" + t);
  function find(q, g) {
    const raw = (q || "").toLocaleLowerCase("tr").split(/\s+/).filter(Boolean), toks = raw.map(norm);
    const cities = toks.length ? idx.c.filter(c => toks.every(t => (" " + c.h).includes(" " + t))) : [];
    cities.sort((a, b) => raw.every(t => a.r.startsWith(t)) ? -1 : raw.every(t => b.r.startsWith(t)) ? 1 : 0);
    const places = idx.p.filter(p => (g === "" || p[5] === +g) && toks.every(t => wordHas(p.h, t)));
    const ilceler = new Map();
    for (const p of places) if (p[2] && toks.some(t => p.i === t)) {
      const k = p[1] + "|" + p[2]; ilceler.set(k, (ilceler.get(k) || 0) + 1);
    }
    if (toks.length) {
      const score = p => (toks.some(t => p.i === t || idx.c[p[1]].h === t) ? 0 : 8) + (raw.every(t => wordHas(p.r, t)) ? 0 : 4)
        + (p.n.startsWith(toks[0]) ? 0 : wordHas(" " + p.n, toks[0]) ? 1 : 2);
      for (const p of places) p.s = score(p);
      places.sort((a, b) => a.s - b.s);
    }
    // "kaş" yazana Kastamonu'yu değil Kaş'ı öner: Türkçe harfleri birebir tutan il/ilçe varsa yalnız onları göster
    const exact = cities.filter(c => raw.every(t => (" " + c.r).includes(" " + t)));
    const shown = exact.length || ilceler.size ? exact : cities;
    return { cities: shown, places, ilceler: [...ilceler].map(([k, n]) => { const [ci, il] = k.split("|"); return [idx.c[+ci], il, n]; }) };
  }
  const cityUrl = c => root + c[0] + "/";
  const ilceUrl = (c, il) => cityUrl(c) + "?ilce=" + encodeURIComponent(il);
  const placeUrl = p => root + idx.c[p[1]][0] + "/#p-" + p[4];

  // Üst menüdeki arama kutusu
  const top = document.querySelector("form.q");
  if (top) {
    const inp = top.querySelector("input"), dd = top.querySelector(".dd");
    let sel = -1;
    const links = () => [...dd.querySelectorAll("a")];
    const mark = () => links().forEach((a, i) => a.classList.toggle("on", i === sel));
    const show = async () => {
      const q = inp.value.trim();
      if (q.length < 2) { dd.hidden = true; return; }
      await load();
      const { cities, places, ilceler } = find(q, "");
      const top = cities.slice(0, 3).map(c => `<a href="${cityUrl(c)}"><b>${esc(c[1])}</b><span>İl · ${c[2]} yer</span></a>`)
        .concat(ilceler.slice(0, 3).map(([c, il, n]) => `<a href="${ilceUrl(c, il)}"><b>${esc(il)}</b><span>İlçe · ${esc(c[1])} · ${n} yer</span></a>`));
      const rows = top.concat(places.slice(0, Math.max(4, 8 - top.length)).map(p =>
          `<a href="${placeUrl(p)}"><b>${esc(p[0])}</b><span>${esc(idx.t[p[3]])} · ${esc(idx.c[p[1]][1])}${p[2] ? " / " + esc(p[2]) : ""}</span></a>`));
      const more = places.length > rows.length - top.length ? `<a class="all" href="${root}?q=${encodeURIComponent(q)}">Tüm sonuçlar (${places.length})</a>` : "";
      dd.innerHTML = rows.length ? rows.join("") + more : `<p>“${esc(q)}” için sonuç yok.</p>`;
      dd.hidden = false; sel = -1;
    };
    inp.addEventListener("focus", load, { once: true });
    inp.addEventListener("input", show);
    inp.addEventListener("keydown", ev => {
      const a = links();
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        if (dd.hidden || !a.length) return;
        ev.preventDefault();
        sel = ev.key === "ArrowDown" ? (sel + 1) % a.length : sel <= 0 ? a.length - 1 : sel - 1; mark();
      } else if (ev.key === "Enter" && sel >= 0 && a[sel]) {
        ev.preventDefault(); location.href = a[sel].href;
      } else if (ev.key === "Escape") dd.hidden = true;
    });
    document.addEventListener("click", ev => { if (!top.contains(ev.target)) dd.hidden = true; });
  }

  // Ana sayfadaki arama: sonuçlar tablo olarak
  const form = document.getElementById("ara");
  if (form) {
    const q = document.getElementById("ara-q"), t = document.getElementById("ara-t"), out = document.getElementById("sonuc");
    let limit = 50;
    const render = async (push) => {
      const v = q.value.trim(), g = t.value;
      if (push) {
        const u = new URL(location.href);
        v ? u.searchParams.set("q", v) : u.searchParams.delete("q");
        g ? u.searchParams.set("t", g) : u.searchParams.delete("t");
        history.replaceState(null, "", u);
      }
      if (!v && !g) { out.innerHTML = ""; return; }
      await load();
      const { cities, places, ilceler } = find(v, g);
      const links = cities.map(c => `<a href="${cityUrl(c)}">${esc(c[1])}</a> (il, ${c[2]} yer)`)
        .concat(ilceler.slice(0, 6).map(([c, il, n]) => `<a href="${ilceUrl(c, il)}">${esc(il)}, ${esc(c[1])}</a> (ilçe, ${n} yer)`));
      const head = links.length ? `<p class="iller-bul">Sayfaya git: ${links.join(" · ")}</p>` : "";
      if (!places.length) { out.innerHTML = head + `<p class="yok">“${esc(v)}” için yer bulunamadı. İl ya da ilçe adıyla dene.</p>`; return; }
      const rows = places.slice(0, limit).map(p => `<tr><td><a href="${placeUrl(p)}">${esc(p[0])}</a></td><td>${esc(idx.t[p[3]])}</td>` +
        `<td>${esc(idx.c[p[1]][1])}</td><td>${esc(p[2] || "Merkez")}</td></tr>`).join("");
      const more = places.length > limit ? `<button type="button" class="daha">${places.length - limit} sonuç daha göster</button>` : "";
      out.innerHTML = head + `<p class="adet">${places.length} yer bulundu</p><table class="liste kisa"><thead><tr><th>Ad</th><th>Tür</th><th>İl</th><th>İlçe</th></tr></thead>` +
        `<tbody>${rows}</tbody></table>${more}`;
    };
    out.addEventListener("click", ev => { if (ev.target.classList.contains("daha")) { limit += 200; render(false); } });
    let timer;
    q.addEventListener("input", () => { clearTimeout(timer); limit = 50; timer = setTimeout(() => render(true), 150); });
    t.addEventListener("change", () => { limit = 50; render(true); });
    form.addEventListener("submit", ev => { ev.preventDefault(); limit = 50; render(true); });
    const params = new URLSearchParams(location.search);
    q.value = params.get("q") || ""; t.value = params.get("t") || "";
    if (q.value || t.value) render(false);
  }
})();
