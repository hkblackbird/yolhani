// Site içi hızlı arama: il, ilçe ve yer adlarında arar, açılır listede önerir.
// Dizin (ara.json) kutuya ilk odaklanıldığında yüklenir.
(() => {
  const root = document.currentScript.dataset.root || "";
  const low = s => (s || "").toLocaleLowerCase("tr");
  const norm = s => low(s).replace(/ı/g, "i").normalize("NFD").replace(/[̀-ͯ]/g, "");
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
  let idx, loading;
  const load = () => loading ||= fetch(root + "ara.json").then(r => r.json()).then(d => {
    for (const c of d.c) { c.h = norm(c[1]); c.r = low(c[1]); }
    for (const p of d.p) {
      p.n = norm(p[0]); p.i = norm(p[2]);
      p.h = " " + p.n + " " + d.c[p[1]].h + " " + p.i + " " + norm(d.t[p[3]]);
      p.r = " " + low(p[0]) + " " + d.c[p[1]].r + " " + low(p[2]) + " " + low(d.t[p[3]]);
    }
    return idx = d;
  });

  // Sözcük başında eşleşme; Türkçe harfleri birebir tutan ve il/ilçe adıyla tam eşleşen sonuçlar öne çıkar
  const wordHas = (h, t) => h.includes(" " + t) || h.includes("(" + t) || h.includes("-" + t);
  function find(q) {
    const raw = low(q).split(/\s+/).filter(Boolean), toks = raw.map(norm);
    const places = idx.p.filter(p => toks.every(t => wordHas(p.h, t)));
    const ilceler = new Map();
    for (const p of places) if (p[2] && toks.some(t => p.i === t)) {
      const k = p[1] + "|" + p[2]; ilceler.set(k, (ilceler.get(k) || 0) + 1);
    }
    let cities = idx.c.filter(c => toks.every(t => (" " + c.h).includes(" " + t)));
    const exact = cities.filter(c => raw.every(t => (" " + c.r).includes(" " + t)));
    if (exact.length || ilceler.size) cities = exact;   // "kaş" yazana Kastamonu'yu değil Kaş'ı öner
    const score = p => (toks.some(t => p.i === t || idx.c[p[1]].h === t) ? 0 : 8) + (raw.every(t => wordHas(p.r, t)) ? 0 : 4)
      + (p.n.startsWith(toks[0]) ? 0 : wordHas(" " + p.n, toks[0]) ? 1 : 2);
    for (const p of places) p.s = score(p);
    places.sort((a, b) => a.s - b.s);
    return { cities, places, ilceler: [...ilceler].map(([k, n]) => { const [ci, il] = k.split("|"); return [idx.c[+ci], il, n]; }) };
  }
  const cityUrl = c => root + c[0] + "/";
  const ilceUrl = (c, il) => cityUrl(c) + "?ilce=" + encodeURIComponent(il);
  const placeUrl = p => root + idx.c[p[1]][0] + "/#p-" + p[4];

  for (const form of document.querySelectorAll("form.q")) {
    const inp = form.querySelector("input"), dd = form.querySelector(".dd");
    let sel = -1;
    const links = () => [...dd.querySelectorAll("a")];
    const mark = () => links().forEach((a, i) => a.setAttribute("aria-selected", i === sel));
    const show = async () => {
      const q = inp.value.trim();
      if (q.length < 2) { dd.hidden = true; inp.setAttribute("aria-expanded", "false"); return; }
      await load();
      const { cities, places, ilceler } = find(q);
      const top = cities.slice(0, 3).map(c => `<a href="${cityUrl(c)}" role="option"><b>${esc(c[1])}</b><span>İl · ${c[2]} yer</span></a>`)
        .concat(ilceler.slice(0, 3).map(([c, il, n]) => `<a href="${ilceUrl(c, il)}" role="option"><b>${esc(il)}</b><span>İlçe · ${esc(c[1])} · ${n} yer</span></a>`));
      const rows = top.concat(places.slice(0, Math.max(4, 8 - top.length)).map(p =>
        `<a href="${placeUrl(p)}" role="option"><b>${esc(p[0])}</b><span>${esc(idx.t[p[3]])} · ${esc(idx.c[p[1]][1])}${p[2] ? " / " + esc(p[2]) : ""}</span></a>`));
      dd.innerHTML = rows.length ? rows.join("") : `<p>“${esc(q)}” için sonuç yok. İl ya da ilçe adıyla dene.</p>`;
      dd.hidden = false; inp.setAttribute("aria-expanded", "true"); sel = rows.length ? 0 : -1; mark();
    };
    inp.addEventListener("focus", load, { once: true });
    inp.addEventListener("input", show);
    inp.addEventListener("keydown", ev => {
      const a = links();
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        if (dd.hidden || !a.length) return;
        ev.preventDefault();
        sel = ev.key === "ArrowDown" ? (sel + 1) % a.length : sel <= 0 ? a.length - 1 : sel - 1; mark();
      } else if (ev.key === "Escape") { dd.hidden = true; }
    });
    form.addEventListener("submit", async ev => {
      ev.preventDefault();
      if (dd.hidden) await show();
      const a = links()[Math.max(sel, 0)];
      if (a) location.href = a.href;
    });
    document.addEventListener("click", ev => { if (!form.contains(ev.target)) dd.hidden = true; });
  }
})();
