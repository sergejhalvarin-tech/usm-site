import { createContext, useCallback, useContext, useEffect, useId, useRef, useState } from "react";

/* Equipment picker (hero card) + «Куда отправить предложение?» dialog.
   Floating panels announce themselves to the mascot via window events so «Огонёк» can jump onto them. */
export const RAW = [
  { v: "birch", label: "Берёза", hint: "≈150 кг угля с 1 м³" },
  { v: "pine", label: "Сосна", hint: "≈120 кг угля с 1 м³" },
  { v: "larch", label: "Лиственница", hint: "≈160 кг угля с 1 м³" },
  { v: "mixed", label: "Смешанное сырьё", hint: "подберём режим под смесь" },
  { v: "other", label: "Другое", hint: "уточним при звонке" },
  { v: "unknown", label: "Пока не определился", hint: "поможем выбрать" },
];
export const OUTPUT = [
  { v: "50", label: "до 50 т/месяц", kilns: 2 },
  { v: "100", label: "до 100 т/месяц", kilns: 3 },
  { v: "100+", label: "свыше 100 т/месяц", kilns: 4 },
  { v: "help", label: "Нужна помощь с расчётом", kilns: null },
];
const PER_KILN = 42;   // t/month, upper value of 26–42

export const focusMascot = (el, tip) => window.dispatchEvent(new CustomEvent("ogonek:focus", { detail: { el, tip } }));
export const releaseMascot = () => window.dispatchEvent(new CustomEvent("ogonek:release"));

/* ---------- accessible custom select (listbox) */
function Select({ label, options, value, onChange, placeholder, tip }) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const btn = useRef(null), panel = useRef(null), id = useId();
  const cur = options.find((o) => o.v === value);
  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, options.findIndex((o) => o.v === value)));
    const t = setTimeout(() => panel.current && focusMascot(panel.current, tip), 30);
    const off = (e) => { if (!panel.current?.contains(e.target) && !btn.current?.contains(e.target)) setOpen(false); };
    document.addEventListener("pointerdown", off);
    return () => { clearTimeout(t); document.removeEventListener("pointerdown", off); releaseMascot(); };
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (o) => { onChange(o.v); setOpen(false); btn.current?.focus(); };
  const onKey = (e) => {
    if (!open && ["ArrowDown", "ArrowUp", "Enter", " "].includes(e.key)) { e.preventDefault(); setOpen(true); return; }
    if (!open) return;
    if (e.key === "Escape") { e.preventDefault(); setOpen(false); }
    else if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(options.length - 1, a + 1)); }
    else if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(0, a - 1)); }
    else if (e.key === "Home") { e.preventDefault(); setActive(0); }
    else if (e.key === "End") { e.preventDefault(); setActive(options.length - 1); }
    else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(options[active]); }
    else if (e.key === "Tab") setOpen(false);
  };
  return (
    <div className={open ? "sel open" : "sel"}>
      <span className="sel-label" id={`${id}-l`}>{label}</span>
      <button ref={btn} type="button" className={cur ? "sel-btn" : "sel-btn empty"} aria-haspopup="listbox" aria-expanded={open}
        aria-labelledby={`${id}-l ${id}-v`} aria-activedescendant={open ? `${id}-o${active}` : undefined} aria-controls={`${id}-list`}
        onClick={() => setOpen(!open)} onKeyDown={onKey}>
        <span id={`${id}-v`}>{cur ? cur.label : placeholder}</span>
        <svg viewBox="0 0 12 8" width="12" height="8" aria-hidden="true"><path d="M1 1.5 6 6.5l5-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" /></svg>
      </button>
      {open && (
        <ul ref={panel} className="sel-panel" role="listbox" id={`${id}-list`} aria-labelledby={`${id}-l`} data-float>
          {options.map((o, i) => (
            <li key={o.v} id={`${id}-o${i}`} role="option" aria-selected={o.v === value}
              className={(i === active ? "act " : "") + (o.v === value ? "sel-on" : "")}
              onPointerEnter={() => setActive(i)} onClick={() => pick(o)}>
              <span data-perch>{o.label}</span>{o.hint && <small>{o.hint}</small>}
              {o.v === value && <svg viewBox="0 0 14 10" width="14" height="10" aria-hidden="true"><path d="m1 5 4 4 8-8" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------- modal shell shared by both popups: focus trap, Esc, scroll lock, mascot hop */
function Modal({ label, tip, wide, onClose, children }) {
  const card = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    document.body.style.overflow = "hidden";
    card.current?.querySelector("input, .sel-btn")?.focus();
    const t = setTimeout(() => card.current && focusMascot(card.current, tip), 260);
    const k = (e) => {
      if (e.key === "Escape" && !card.current?.querySelector(".sel.open")) onClose();
      if (e.key === "Tab" && card.current) {   // keep focus inside the dialog
        const f = [...card.current.querySelectorAll("button, input, a[href]")];
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    window.addEventListener("keydown", k);
    return () => { clearTimeout(t); window.removeEventListener("keydown", k); document.body.style.overflow = ""; releaseMascot(); prev?.focus?.(); };
  }, [onClose, tip]);
  return (
    <div className="dlg-back" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={wide ? "dlg dlg-pick" : "dlg"} ref={card} role="dialog" aria-modal="true" aria-labelledby={label} data-float>
        <button className="dlg-x" onClick={onClose} aria-label="Закрыть">×</button>
        {children({ card })}
      </div>
    </div>
  );
}

/* ---------- «Куда отправить предложение?» */
function OfferDialog({ summary, onClose }) {
  const [sent, setSent] = useState(false);
  return (
    <Modal label="dlg-t" tip="Оставь контакты — пришлём комплектацию и цену" onClose={onClose}>
      {({ card }) => !sent ? (
        <>
          <h3 id="dlg-t" data-perch>Куда отправить предложение?</h3>
          <p className="dlg-sub">Уточним задачу и подготовим комплектацию с расчётом стоимости.</p>
          {summary?.length > 0 && <div className="dlg-chips">{summary.map((s) => <span key={s}>{s}</span>)}</div>}
          <form onSubmit={(e) => { e.preventDefault(); setSent(true); setTimeout(() => card.current && focusMascot(card.current, "Ура! Инженер скоро позвонит 🔥"), 60); }}>
            <label className="fld"><input required name="name" autoComplete="name" placeholder=" " /><span>Ваше имя</span></label>
            <label className="fld"><input required name="contact" autoComplete="tel" placeholder=" " /><span>Телефон или email</span></label>
            <button className="btn btn-fire full" type="submit">Получить предложение <span aria-hidden="true">→</span></button>
            <p className="dlg-legal">Нажимая на кнопку, вы соглашаетесь с <a href="#contact" onClick={onClose}>политикой конфиденциальности</a> и даёте согласие на обработку персональных данных.</p>
          </form>
        </>
      ) : (
        <div className="dlg-done" role="status">
          <span className="dlg-ok" aria-hidden="true">✓</span>
          <h3 id="dlg-t" data-perch>Предложение готовим</h3>
          <p className="dlg-sub">Инженер свяжется в течение рабочего дня. Это демо-версия сайта — заявка пока никуда не отправляется.</p>
          <button className="btn full" onClick={onClose}>Готово</button>
        </div>
      )}
    </Modal>
  );
}

/* ---------- «Подобрать оборудование» */
function PickerDialog({ onClose, onDone }) {
  const [raw, setRaw] = useState("birch");
  const [out, setOut] = useState("50");
  const r = RAW.find((x) => x.v === raw), o = OUTPUT.find((x) => x.v === out);
  const rec = !o ? null : o.kilns == null ? { big: "Посчитаем вместе", small: "инженер подберёт состав под ваше сырьё" }
    : o.v === "100+" ? { big: "Линия от 4 печей", small: `проект участка · ${o.kilns * PER_KILN}+ т/мес` }
    : { big: `${o.kilns} печи USM`, small: `до ${o.kilns * PER_KILN} т угля в месяц · ${r.hint}` };
  return (
    <Modal label="pick-t" wide tip="Выбери сырьё и объём — подскажу, сколько печей нужно" onClose={onClose}>
      {() => (
        <div className="picker">
          <h3 id="pick-t" className="picker-t" data-perch>Подобрать оборудование</h3>
          <p className="dlg-sub">Два вопроса — и покажем, какая комплектация вам подходит.</p>
          <Select label="Сырьё" options={RAW} value={raw} onChange={setRaw} placeholder="Выберите сырьё" tip="От породы зависит выход угля" />
          <Select label="Плановый выпуск угля" options={OUTPUT} value={out} onChange={setOut} placeholder="Укажите объём" tip="Одна печь даёт 26–42 т угля в месяц" />
          {rec && (
            <div className="picker-rec" aria-live="polite">
              <span className="picker-rec-k">Рекомендуем</span>
              <strong>{rec.big}</strong>
              <small>{rec.small}</small>
            </div>
          )}
          <button className="btn btn-fire full" onClick={() => onDone([r.label, o.label, rec?.big].filter(Boolean))}>Подобрать комплектацию <span aria-hidden="true">→</span></button>
        </div>
      )}
    </Modal>
  );
}

/* ---------- provider: header buttons open either popup */
const OfferCtx = createContext({ open: () => {}, openPicker: () => {} });
export const useOffer = () => useContext(OfferCtx);

export function OfferProvider({ children }) {
  const [view, setView] = useState(null);   // null | { kind: "pick" } | { kind: "offer", summary }
  const open = useCallback((summary = []) => setView({ kind: "offer", summary }), []);
  const openPicker = useCallback(() => setView({ kind: "pick" }), []);
  const close = useCallback(() => setView(null), []);
  return (
    <OfferCtx.Provider value={{ open, openPicker }}>
      {children}
      {view?.kind === "pick" && <PickerDialog onClose={close} onDone={open} />}
      {view?.kind === "offer" && <OfferDialog key="offer" summary={view.summary} onClose={close} />}
    </OfferCtx.Provider>
  );
}
