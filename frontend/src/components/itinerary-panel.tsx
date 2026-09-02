import type { PlanVersion } from "@/lib/conversation-api";

type ItineraryPanelProps = {
  planVersion: PlanVersion;
};

export function ItineraryPanel({ planVersion }: ItineraryPanelProps) {
  const { plan } = planVersion;

  return (
    <div className="itinerary-panel">
      <header className="itinerary-header">
        <span className="panel-kicker">行程方案 · V{planVersion.version}</span>
        <h2>{plan.title}</h2>
        <p>{plan.overview}</p>
      </header>

      <div className="itinerary-card">
        <div className="itinerary-days">
          {plan.days.map((day) => {
            const spots = day.items.flatMap((item) => item.photo_spots).slice(0, 3);
            return (
              <section className="day-section" key={day.day_index}>
                <div className="day-head">
                  <span className="day-number">DAY {day.day_index}</span>
                  <h3>{day.theme || `北京探索第 ${day.day_index} 天`}</h3>
                  <span className="day-date">{day.date || "日期待定"}</span>
                </div>

                <ol className="route-list">
                  {day.items.map((item, index) => {
                    const toNext = day.items[index + 1]?.route_from_previous;
                    return (
                      <li className="route-stop" key={item.item_id}>
                        <span className="route-time">{item.start_time || "—"}</span>
                        <span className="route-axis" aria-hidden="true">
                          <i className="route-dot" />
                        </span>
                        <div className="stop-copy">
                          <strong>{item.poi.canonical_name}</strong>
                          <div className="stop-meta">
                            {item.booking_reminder ? (
                              <span className="stop-booking">建议提前预约</span>
                            ) : null}
                            {item.entry_tip ? (
                              <span className="stop-entry">{item.entry_tip}</span>
                            ) : null}
                            <span className="stop-duration">建议停留 {item.stay_duration_min} 分钟</span>
                          </div>
                          {toNext ? (
                            <span className="stop-transfer">
                              到下一个景点：{toNext.recommended_mode} · {toNext.duration_min} 分钟
                            </span>
                          ) : null}
                        </div>
                      </li>
                    );
                  })}
                </ol>

                {spots.length > 0 ? (
                  <section className="photo-spots" aria-label="出片点">
                    <div className="photo-spots-head">
                      <strong>出片点</strong>
                      <span>站在这些位置更容易出片</span>
                    </div>
                    <div className="spot-grid">
                      {spots.map((spot) => {
                        const cover = spot.reference_photos?.[0];
                        return (
                          <article className="spot-card" key={spot.spot_id}>
                            {cover ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                className="spot-image"
                                src={cover.thumbnail_url ?? cover.storage_url}
                                alt={`${spot.spot_name} 参考照片`}
                                referrerPolicy="no-referrer"
                              />
                            ) : null}
                            <div className="spot-body">
                              <h4>{spot.spot_name}</h4>
                              <p className="spot-detail">{spot.location_description}</p>
                              {spot.best_time ? (
                                <span className="spot-time">{spot.best_time.display_text}</span>
                              ) : null}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </section>
                ) : null}
              </section>
            );
          })}
        </div>
      </div>

      {plan.lodging_recommendations?.length ? (
        <section className="stay-section" aria-label="住宿区域推荐">
          <div className="stay-head">
            <strong>住宿区域推荐</strong>
            <span>这里只推荐区域，不推荐具体酒店</span>
          </div>
          {plan.lodging_recommendations.map((lodging) => (
            <div className="stay-item" key={lodging.area_id}>
              <span className="stay-badge">{lodging.level}</span>
              <div className="stay-copy">
                <strong>
                  {lodging.name}
                  {lodging.representative_station ? ` · ${lodging.representative_station}` : ""}
                </strong>
                <span>{lodging.reason}</span>
              </div>
            </div>
          ))}
        </section>
      ) : null}
    </div>
  );
}
