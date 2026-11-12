import { lazy, Suspense, useEffect, useState } from "react";
import { Logo } from "./Brand.jsx";
import { Mascot } from "./Mascot.jsx";
import { contacts, heroStats, specs, steps, tel } from "./data.js";
import { OfferProvider, useOffer } from "./Picker.jsx";

const KilnExplorer = lazy(() => import("./KilnExplorer.jsx").then((m) => ({ default: m.KilnExplorer })));
const DeliveryMap = lazy(() => import("./DeliveryMap.jsx").then((m) => ({ default: m.DeliveryMap })));
const ProcessViz = lazy(() => import("./ProcessViz.jsx").then((m) => ({ default: m.ProcessViz })));
const Skeleton = ({ label }) => <div className="stage skeleton">{label}</div>;

function Header() {
  const { open, openPicker } = useOffer();
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => { const on = () => setScrolled(window.scrollY > 8); on(); window.addEventListener("scroll", on, { passive: true }); return () => window.removeEventListener("scroll", on); }, []);
  return (
    <header className={scrolled ? "header scrolled" : "header on-dark"}>
      <div className="wrap header-in">
        <a href="#top" className="brand" aria-label="USM — наверх"><Logo /></a>
        <nav className="nav" aria-label="Разделы">
          <a href="#equipment">Печь</a><a href="#process">Как работает</a><a href="#specs">Характеристики</a><a href="#geo">География</a><a href="#contact">Контакты</a>
        </nav>
        <a className="header-phone" href={tel(contacts.phones[0])}>{contacts.phones[0]}</a>
        <div className="header-cta">
          <button className="btn btn-sm btn-fire" onClick={openPicker} aria-label="Подобрать оборудование">Подобрать<span className="hide-sm"> оборудование</span></button>
          <button className="btn btn-sm btn-fire" onClick={() => open([])}>Получить расчёт</button>
        </div>
      </div>
    </header>
  );
}

function SectionHead({ n, title, text }) {
  return (
    <div className="shead">
      <span className="snum">{n}</span>
      <h2 data-perch>{title}</h2>
      {text && <p>{text}</p>}
    </div>
  );
}

function ContactForm() {
  const [sent, setSent] = useState(false);
  if (sent) return <div className="form-done" role="status"><strong>Спасибо! Заявка принята.</strong><span>Это демо-версия сайта — заявка пока никуда не отправляется.</span></div>;
  return (
    <form className="form" onSubmit={(e) => { e.preventDefault(); setSent(true); }}>
      <label><span>Имя</span><input required name="name" autoComplete="name" /></label>
      <label><span>Телефон</span><input required name="phone" type="tel" autoComplete="tel" inputMode="tel" /></label>
      <label className="full"><span>Сырьё и план по углю</span><input name="task" placeholder="Например: берёза, 30 т в месяц" /></label>
      <label className="check full"><input type="checkbox" required /> <span>Согласен на обработку персональных данных</span></label>
      <button className="btn full" type="submit">Получить расчёт</button>
    </form>
  );
}

export function App() {
  return (
    <OfferProvider>
    <div className="page">
      <Header />
      <main>
        <section id="top" className="hero">
          <div className="hero-bg" aria-hidden="true"><span className="hero-glow" /><span className="hero-ring" /><span className="hero-floor" /></div>
          <div className="wrap hero-grid">
            <div className="hero-text">
              <p className="kicker"><span className="dot" />Ретортные углевыжигательные печи · собственное производство</p>
              <h1 data-perch>Древесный уголь без дыма и&nbsp;ручного контроля</h1>
              <p className="lead">Печь USM сжигает собственный пиролизный газ и ведёт цикл по автоматике — от розжига до остывания.</p>
              <div className="hero-cta">
                <a className="btn btn-light" href="#equipment">Смотреть печь в 3D <span aria-hidden="true">↓</span></a>
                <a className="link-light" href={tel(contacts.phones[0])}>{contacts.phones[0]}</a>
              </div>
              <dl className="stats">
                {heroStats.map((s) => <div key={s.l}><dt data-perch>{s.v}<small> {s.u}</small></dt><dd>{s.l}</dd></div>)}
              </dl>
            </div>
            <div className="hero-stage">
              <figure className="hero-art" data-hide>
                <img src={`${import.meta.env.BASE_URL}assets/kiln_hero.webp`} alt="Углевыжигательная печь USM: графитовый корпус, оранжевые загрузочные двери, дымовые трубы и шкаф автоматики" width="1600" height="1335" />
              </figure>
              <p className="hero-note"><span>+</span>Система просушки сырья — в базовой комплектации</p>
            </div>
          </div>
        </section>

        <section id="equipment" className="section">
          <div className="wrap">
            <SectionHead n="01" title="Печь и оборудование" text="Модель построена по чертежу УП040.003-4. Выберите узел — печь повернётся к нему; внутренние узлы открываются в разрезе." />
            <Suspense fallback={<Skeleton label="Загружаем модель печи…" />}><KilnExplorer /></Suspense>
          </div>
        </section>

        <section id="process" className="section section-alt">
          <div className="wrap">
            <SectionHead n="02" title="Видимые детали" text="Полный цикл — около 22 часов — за 36 секунд. Это расчёт по физической модели: теплопередача в штабеле, кинетика разложения древесины, горение газа, тяга и автоматика." />
            <Suspense fallback={<Skeleton label="Загружаем печь в разрезе…" />}><ProcessViz /></Suspense>
          </div>
        </section>

        <section id="specs" className="section">
          <div className="wrap specs">
            <SectionHead n="03" title="Характеристики" />
            <table className="spec-table"><tbody>{specs.map(([k, v]) => <tr key={k}><th scope="row">{k}</th><td>{v}</td></tr>)}</tbody></table>
          </div>
        </section>

        <section id="steps" className="section section-alt">
          <div className="wrap">
            <SectionHead n="04" title="Как мы работаем" />
            <ol className="steps">{steps.map((s) => <li key={s.n}><span>{s.n}</span><h3 data-perch>{s.t}</h3><p>{s.d}</p></li>)}</ol>
          </div>
        </section>

        <section id="geo" className="section geo-sec">
          <div className="wrap">
            <SectionHead n="05" title="География поставок" text="Поставляем оборудование по России и за рубеж. Условия доставки согласуем под ваш проект." />
            <Suspense fallback={<Skeleton label="Загружаем карту…" />}><DeliveryMap /></Suspense>
          </div>
        </section>

        <section id="contact" className="section contact">
          <div className="wrap contact-in">
            <div>
              <h2 data-perch>Рассчитаем печь под ваше сырьё</h2>
              <p className="lead">Инженер перезвонит в течение рабочего дня, уточнит сырьё и площадку и пришлёт расчёт комплектации.</p>
              <ul className="contact-list">
                {contacts.phones.map((p) => <li key={p}><a href={tel(p)}>{p}</a></li>)}
                <li><a href={`mailto:${contacts.email}`}>{contacts.email}</a></li>
                <li><span>Офис и производство: {contacts.address}</span></li>
              </ul>
            </div>
            <ContactForm />
          </div>
        </section>
      </main>
      <footer className="footer"><div className="wrap footer-in"><Logo size={20} /><span>Оборудование для производства древесного угля</span><span>© {new Date().getFullYear()}</span></div></footer>
      <Mascot />
    </div>
    </OfferProvider>
  );
}
