import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Camera,
  Check,
  Clock3,
  MapPin,
  Route,
  ShieldCheck,
  Sparkles,
  SunMedium,
} from "lucide-react";
import { TripStarter } from "@/components/trip-starter";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "PicPal｜顺路又出片的北京行程",
  description:
    "说出旅行天数、同行人和拍摄偏好，PicPal 会生成包含逐站时间、交通、预约提醒和沿途出片点的北京行程。",
};

const defaultPrompt =
  "我想去北京玩3天，节奏轻松一些，喜欢经典建筑，也想沿途拍到好看的照片。";

export default function HomePage() {
  return (
    <div className={styles.site}>
      <a className={styles.skipLink} href="#main-content">
        跳到主要内容
      </a>

      <div className={styles.pageFrame}>
        <header className={styles.header}>
          <nav className={styles.nav} aria-label="官网导航">
            <Link className={styles.brand} href="/" aria-label="PicPal 首页">
              <Image
                className={styles.brandLogo}
                src="/brand/picpal-logo.png"
                alt=""
                width={1200}
                height={370}
                sizes="112px"
                priority
                loading="eager"
                unoptimized
              />
            </Link>

            <div className={styles.navLinks}>
              <a className={styles.activeNavLink} href="#product">
                产品介绍
              </a>
              <a href="#route-map">行程示例</a>
              <a href="#why-picpal">为什么是 PicPal</a>
            </div>

            <div className={styles.navActions}>
              <span>北京试点</span>
              <Link className={styles.navCta} href="/plan">
                开始规划
                <ArrowRight size={14} aria-hidden="true" />
              </Link>
            </div>
          </nav>
        </header>

        <main id="main-content">
          <section className={styles.hero} id="product" aria-labelledby="hero-title">
            <div className={styles.heroCopy}>
              <p className={styles.eyebrow}>
                <span aria-hidden="true" />
                北京试点 · AI 旅行规划与出片点推荐
              </p>
              <h1 id="hero-title">
                把想去的北京，
                <span>排成顺路又出片的一程</span>
              </h1>
              <p className={styles.heroLead}>
                说出同行的人、旅行天数和喜欢的内容，PicPal 会把逐站时间、交通衔接、预约提醒，
                以及沿途值得拍的位置整理成一份可执行行程。
              </p>

              <TripStarter />

              <p className={styles.starterNote}>
                <Sparkles size={13} aria-hidden="true" />
                日期还没定也可以开始，后续能在对话里继续调整
              </p>
            </div>

            <figure
              className={styles.mapStage}
              id="route-map"
              data-route-map
              aria-labelledby="map-caption"
            >
              <svg
                className={styles.cityMap}
                viewBox="0 0 1200 560"
                preserveAspectRatio="xMidYMid slice"
                aria-hidden="true"
                focusable="false"
              >
                <defs>
                  <pattern id="map-dots" width="22" height="22" patternUnits="userSpaceOnUse">
                    <circle cx="1" cy="1" r="0.75" fill="#d9d6cf" opacity="0.65" />
                  </pattern>
                  <filter id="route-shadow" x="-20%" y="-20%" width="140%" height="140%">
                    <feDropShadow dx="0" dy="5" stdDeviation="6" floodColor="#8b8982" floodOpacity="0.18" />
                  </filter>
                </defs>

                <rect width="1200" height="560" fill="#f7f6f1" />
                <rect width="1200" height="560" fill="url(#map-dots)" />

                <g className={styles.districtBlocks}>
                  <path d="M55 57L286 29L349 133L305 229L86 206Z" />
                  <path d="M370 34L585 52L564 169L354 164Z" />
                  <path d="M640 42L862 30L907 137L737 185L628 136Z" />
                  <path d="M931 42L1150 72L1127 216L927 197L886 134Z" />
                  <path d="M47 264L274 232L342 341L281 463L52 437Z" />
                  <path d="M342 209L548 191L553 388L350 401L307 320Z" />
                  <path d="M651 204L871 177L916 359L750 404L643 341Z" />
                  <path d="M931 232L1158 213L1141 442L925 431L885 346Z" />
                  <path d="M326 437L530 411L594 545L346 547L284 494Z" />
                  <path d="M626 415L842 405L889 542L624 545Z" />
                </g>

                <g className={styles.waterAreas}>
                  <path d="M408 88C438 54 495 59 515 93C531 121 504 143 468 143C429 144 384 126 408 88Z" />
                  <path d="M432 151C448 131 479 134 491 157C503 180 484 207 458 207C428 207 413 176 432 151Z" />
                  <path d="M244 466C284 430 361 445 373 494C381 524 337 542 284 531C232 520 214 493 244 466Z" />
                </g>

                <g className={styles.minorRoads}>
                  <path d="M10 126C205 111 304 155 459 134S735 94 1190 125" />
                  <path d="M4 186C183 207 282 167 423 190S744 228 1196 187" />
                  <path d="M6 257C189 235 278 285 433 264S742 245 1196 270" />
                  <path d="M6 330C159 309 277 354 419 333S731 315 1195 338" />
                  <path d="M8 414C170 389 316 435 463 408S791 397 1192 421" />
                  <path d="M101 4C115 141 94 271 128 557" />
                  <path d="M218 3C245 139 210 322 238 557" />
                  <path d="M355 4C326 162 386 297 349 558" />
                  <path d="M460 0C489 139 439 346 482 559" />
                  <path d="M726 0C687 156 740 321 704 559" />
                  <path d="M838 0C874 152 823 301 866 559" />
                  <path d="M998 0C963 134 1014 326 984 559" />
                  <path d="M1107 2C1139 146 1098 348 1129 558" />
                  <path d="M38 493C229 353 332 310 479 248S775 131 1155 31" />
                  <path d="M35 49C196 166 316 232 450 289S777 407 1156 532" />
                </g>

                <g className={styles.majorRoads}>
                  <path d="M157 80C329 12 820 11 1026 96C1120 135 1162 232 1137 348C1106 492 930 541 649 543C352 545 137 509 76 385C15 261 45 125 157 80Z" />
                  <path d="M24 373C288 365 453 371 603 372S931 369 1178 377" />
                  <path d="M601 9C591 131 603 263 600 372S609 477 602 559" />
                  <path d="M303 531C423 395 520 335 613 276S827 132 954 29" />
                </g>

                <g className={styles.landmarkZones}>
                  <path d="M550 206H645V349H550Z" />
                  <path d="M565 229H629V330H565Z" />
                  <path d="M651 475C678 452 730 457 753 489C774 519 746 542 700 541C656 540 624 516 651 475Z" />
                </g>

                <g className={styles.mapLabels}>
                  <text x="249" y="316">西城区</text>
                  <text x="849" y="302">东城区</text>
                  <text x="427" y="79">什刹海</text>
                  <text x="716" y="120">南锣鼓巷</text>
                  <text x="783" y="354">王府井</text>
                  <text x="619" y="454">前门</text>
                  <text x="723" y="525">天坛</text>
                  <text className={styles.axisLabel} x="615" y="171">北京中轴线</text>
                </g>

                <g className={styles.routeLine}>
                  <path
                    className={styles.routeUnderlay}
                    d="M600 372C594 346 602 315 598 280C596 246 584 216 590 188"
                  />
                  <path
                    className={styles.routeProgress}
                    d="M600 372C594 346 602 315 598 280C596 246 584 216 590 188"
                  />
                </g>

                <g className={styles.routeMarkers} filter="url(#route-shadow)">
                  <g className={styles.routeMarkerOne}>
                    <circle cx="600" cy="372" r="15" />
                    <text x="600" y="377">1</text>
                  </g>
                  <g className={styles.routeMarkerTwo}>
                    <circle cx="598" cy="280" r="15" />
                    <text x="598" y="285">2</text>
                  </g>
                  <g className={styles.routeMarkerThree}>
                    <circle cx="590" cy="188" r="15" />
                    <text x="590" y="193">3</text>
                  </g>
                </g>

                <g className={styles.secondaryMarkers}>
                  <circle cx="472" cy="125" r="8" />
                  <circle cx="690" cy="142" r="8" />
                  <circle cx="745" cy="337" r="8" />
                  <circle cx="700" cy="515" r="8" />
                </g>
              </svg>

              <span className={`${styles.photoPin} ${styles.photoPinWest}`} aria-hidden="true">
                <Camera size={14} />
              </span>
              <span className={`${styles.photoPin} ${styles.photoPinEast}`} aria-hidden="true">
                <Camera size={14} />
              </span>
              <span className={`${styles.photoPin} ${styles.photoPinSouth}`} aria-hidden="true">
                <Camera size={14} />
              </span>

              <article className={styles.resultCard} aria-labelledby="route-card-title">
                <header className={styles.resultCardHeader}>
                  <span>为你生成 · 北京 3 日</span>
                  <span className={styles.resultStatus}>
                    <Check size={11} aria-hidden="true" />
                    已排顺
                  </span>
                </header>
                <h2 id="route-card-title">经典中轴与城市漫游</h2>
                <p className={styles.dayMeta}>DAY 01 · 09:00—18:30 · 轻松节奏</p>

                <ol className={styles.routeStops} aria-label="第一天示例路线">
                  <li><span>1</span><strong>天安门</strong></li>
                  <li><span>2</span><strong>故宫</strong></li>
                  <li><span>3</span><strong>景山</strong></li>
                </ol>

                <div className={styles.photoTip}>
                  <SunMedium size={17} aria-hidden="true" />
                  <span>
                    <small>沿途出片点</small>
                    <strong>辑芳亭 · 落日余晖</strong>
                  </span>
                </div>

                <div className={styles.resultTags} aria-label="行程包含内容">
                  <span>预约提醒</span>
                  <span>逐站交通</span>
                  <span>拍摄位置</span>
                </div>

                <Link
                  className={styles.cardLink}
                  href={{ pathname: "/plan", query: { prompt: defaultPrompt } }}
                >
                  生成我的路线
                  <ArrowRight size={14} aria-hidden="true" />
                </Link>
              </article>

              <figcaption className={styles.mapCaption} id="map-caption">
                <strong>北京中轴线 · 路线示意</strong>
                <span>非导航地图，实际出行请以实时导航为准</span>
              </figcaption>
            </figure>
          </section>

          <section className={styles.factBar} aria-label="PicPal 规划能力">
            <div>
              <strong>1—5 日</strong>
              <span>当前可规划行程</span>
            </div>
            <div>
              <strong>按小时</strong>
              <span>安排行程节奏</span>
            </div>
            <div>
              <strong>逐段交通</strong>
              <span>串联每个地点</span>
            </div>
            <div>
              <strong>位置 × 时段</strong>
              <span>提供拍摄建议</span>
            </div>
          </section>

          <section className={styles.valueSection} id="why-picpal" aria-labelledby="value-title">
            <div className={styles.valueCopy}>
              <p className={styles.sectionEyebrow}>
                <span aria-hidden="true" />
                不只是景点清单
              </p>
              <h2 id="value-title">
                一份计划，把去哪、怎么走、哪里拍放在一起
              </h2>
              <div className={styles.valueCopyBottom}>
                <p>
                  PicPal 会先理解同行人、日期、节奏和拍摄偏好，再把景点、停留时间、交通、预约与沿途机位排进同一条时间线。
                </p>
                <Link className={styles.darkCta} href="/plan">
                  开始规划行程
                  <ArrowRight size={15} aria-hidden="true" />
                </Link>
              </div>
            </div>

            <div className={styles.productCanvas} aria-label="PicPal 产品能力示例">
              <article className={styles.preferencePanel}>
                <header>
                  <span className={styles.panelIcon}><Sparkles size={15} aria-hidden="true" /></span>
                  <span>旅行偏好已理解</span>
                </header>
                <p>“带父母去北京，想轻松一点，也想拍古建筑合照。”</p>
                <div className={styles.preferenceTags}>
                  <span>带父母</span>
                  <span>3 天</span>
                  <span>轻松节奏</span>
                  <span>古建筑合照</span>
                </div>
                <small><Clock3 size={12} aria-hidden="true" /> 日期待定，也可以继续规划</small>
              </article>

              <article className={styles.sourcePanel}>
                <span className={styles.shieldIcon}><ShieldCheck size={18} aria-hidden="true" /></span>
                <strong>有依据的出片点</strong>
                <ul>
                  <li><Check size={11} aria-hidden="true" /> 明确位置</li>
                  <li><Check size={11} aria-hidden="true" /> 参考照片</li>
                  <li><Check size={11} aria-hidden="true" /> 来源记录</li>
                </ul>
                <small>通过准入校验后才会进入推荐</small>
              </article>

              <article className={styles.miniMapPanel} aria-labelledby="mini-map-title">
                <header>
                  <span>顺路以后，再安排出片时机</span>
                  <strong id="mini-map-title">故宫 → 景山</strong>
                </header>
                <svg viewBox="0 0 620 245" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
                  <rect width="620" height="245" fill="#efeee8" />
                  <g className={styles.miniRoads}>
                    <path d="M5 45C169 86 301 37 615 66" />
                    <path d="M2 124C160 97 306 148 618 116" />
                    <path d="M5 201C167 162 321 215 616 186" />
                    <path d="M94 2C117 74 79 171 112 244" />
                    <path d="M219 1C184 88 235 164 207 245" />
                    <path d="M395 0C427 78 381 166 414 244" />
                    <path d="M531 2C493 78 546 176 516 244" />
                    <path d="M19 232C156 177 265 129 353 86S506 23 603 5" />
                  </g>
                  <path className={styles.miniRouteUnderlay} d="M273 187C281 152 294 120 314 84C327 61 337 43 344 24" />
                  <path className={styles.miniRoute} d="M273 187C281 152 294 120 314 84C327 61 337 43 344 24" />
                  <g className={styles.miniMarkers}>
                    <circle cx="273" cy="187" r="11" />
                    <circle cx="344" cy="24" r="11" />
                  </g>
                  <text className={styles.miniMapLabel} x="226" y="215">故宫 · 15:30</text>
                  <text className={styles.miniMapLabel} x="357" y="29">景山 · 17:00</text>
                </svg>

                <div className={styles.routeReason}>
                  <Route size={14} aria-hidden="true" />
                  <span><strong>这样排更顺</strong>步行衔接，并赶上景山日落</span>
                </div>
                <div className={styles.miniPhotoTip}>
                  <MapPin size={14} aria-hidden="true" />
                  <span><strong>辑芳亭</strong>落日余晖 · 来源已记录</span>
                </div>
              </article>
            </div>
          </section>

          <section className={styles.finalCta} aria-labelledby="final-cta-title">
            <div>
              <p>下一次出发</p>
              <h2 id="final-cta-title">不必先做一整晚攻略</h2>
            </div>
            <p>从一句想法开始，边聊边补齐信息，最后得到一份能照着走、也知道在哪里停下来拍一张的行程。</p>
            <Link className={styles.finalCtaButton} href="/plan">
              定制专属行程
              <ArrowRight size={17} aria-hidden="true" />
            </Link>
          </section>
        </main>

        <footer className={styles.footer}>
          <Link className={styles.footerBrand} href="/" aria-label="PicPal 首页">
            <Image
              className={styles.footerLogo}
              src="/brand/picpal-logo.png"
              alt=""
              width={1200}
              height={370}
              sizes="88px"
              unoptimized
            />
          </Link>
          <p>北京 AI 旅行规划与出片点推荐</p>
          <div>
            <span>北京试点</span>
            <span>邀请制内测</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
