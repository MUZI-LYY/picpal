import { expect, type Page, test } from "@playwright/test";

test("public homepage introduces PicPal and links to the protected planner", async ({ page }, testInfo) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("把想去的北京");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("排成顺路又出片的一程");
  await expect(
    page.getByRole("heading", { name: "一份计划，把去哪、怎么走、哪里拍放在一起" }),
  ).toBeAttached();

  const starter = page.getByRole("form", { name: "快速开始规划" });
  await expect(starter).toBeVisible();
  await expect(starter.getByLabel("行程天数")).toHaveValue("3");
  await expect(starter.getByLabel("想拍什么")).toHaveValue("经典建筑");

  const primaryAction = page.getByRole("link", { name: "开始规划", exact: true });
  await expect(primaryAction).toHaveAttribute("href", "/plan");

  const homepageMetrics = await page.evaluate(() => {
    const hero = document.querySelector<HTMLElement>("main > section");
    const starterButton = document.querySelector<HTMLElement>('form[aria-label="快速开始规划"] button');
    const primaryRect = starterButton?.getBoundingClientRect();
    return {
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      documentWidth: document.documentElement.scrollWidth,
      heroHeight: hero?.getBoundingClientRect().height ?? 0,
      primaryBottom: primaryRect?.bottom ?? Number.POSITIVE_INFINITY,
    };
  });

  expect(homepageMetrics.documentWidth).toBe(homepageMetrics.viewportWidth);
  expect(homepageMetrics.primaryBottom).toBeLessThan(homepageMetrics.viewportHeight);
  if (testInfo.project.name.startsWith("mobile")) {
    expect(homepageMetrics.heroHeight).toBeLessThan(1000);
  }

  await primaryAction.click();

  await expect(page).toHaveURL(/\/plan$/);
  await expect(page.getByRole("heading", { name: "输入邀请码" })).toBeVisible();
});

test("homepage shows a route map, itinerary result, and product evidence", async ({ page }) => {
  await page.goto("/");

  const routeMap = page.locator("[data-route-map]");
  await expect(routeMap).toBeAttached();
  await expect(routeMap.getByRole("heading", { name: "经典中轴与城市漫游" })).toBeVisible();
  await expect(routeMap.getByText("天安门", { exact: true })).toBeVisible();
  await expect(routeMap.getByText("故宫", { exact: true })).toBeVisible();
  await expect(routeMap.getByText("景山", { exact: true })).toBeVisible();
  await expect(routeMap.getByText("非导航地图，实际出行请以实时导航为准")).toBeVisible();

  const valueTitle = page.getByRole("heading", {
    name: "一份计划，把去哪、怎么走、哪里拍放在一起",
  });
  await valueTitle.scrollIntoViewIfNeeded();
  await expect(valueTitle).toBeVisible();
  await expect(page.getByText("旅行偏好已理解")).toBeVisible();
  await expect(page.getByText("通过准入校验后才会进入推荐")).toBeVisible();
  await expect(page.getByText("故宫 → 景山", { exact: true })).toBeVisible();
});

async function mockEmptyHistory(page: Page) {
  await page.addInitScript(() => window.localStorage.setItem("picpal_invited", "1"));
  await page.route("**/api/v1/conversations?limit=30", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], meta: { has_next: false, next_cursor: null } }),
    }),
  );
}

async function mockCompletedConversation(page: Page) {
  const snapshot = {
    conversation: {
      id: "conv-mobile-result",
      title: "北京经典一日游",
      status: "completed",
      requirements: {
        city: "北京",
        days: 1,
        date_status: "pending",
        start_date: null,
        party_size: null,
        companion_types: [],
        must_include: [],
        must_exclude: [],
        interests: ["经典景点"],
        photo_preferences: ["古建筑"],
        pace: "轻松",
        lodging_text: null,
        transport_preferences: [],
        missing_slots: [],
      },
      latest_plan_id: "plan-mobile-result",
      active_run_id: null,
      created_at: "2026-08-22T08:00:00Z",
      updated_at: "2026-08-22T08:03:00Z",
    },
    messages: [
      {
        id: "msg-user",
        conversation_id: "conv-mobile-result",
        role: "user",
        content_type: "text",
        text: "第一次去北京，想走经典路线，每天别太赶。",
        structured_content: null,
        reply_to_message_id: null,
        run_id: null,
        plan_id: null,
        created_at: "2026-08-22T08:00:00Z",
      },
    ],
    active_run: null,
    latest_plan: {
      id: "plan-mobile-result",
      conversation_id: "conv-mobile-result",
      run_id: "run-mobile-result",
      version: 1,
      base_plan_id: null,
      status: "validated",
      changed_days: [1],
      change_summary: ["生成第一版北京行程"],
      plan: {
        schema_version: "1.2.0",
        plan_id: "plan-mobile-result",
        request_id: "request-mobile-result",
        status: "validated",
        title: "北京经典与城市漫游 1 日",
        overview: "从王府井附近出发，游览故宫并返回住宿区域。",
        request_summary: { days: 1, date_status: "pending", pace: "轻松" },
        days: [
          {
            day_index: 1,
            date: null,
            theme: "皇城中轴线",
            start_time: "09:00",
            end_time: "17:30",
            origin: { type: "recommended_area", poi_id: "map:wangfujing", name: "王府井" },
            outbound_route: null,
            items: [
              {
                item_id: "d1-i1",
                poi: { poi_id: "map:forbidden-city", canonical_name: "故宫博物院", map_source: "amap" },
                start_time: "09:30",
                end_time: "15:30",
                stay_duration_min: 360,
                booking_reminder: "建议提前通过官方渠道预约门票",
                entry_tip: "从午门进入，神武门出",
                route_from_previous: null,
                photo_spots: [],
              },
            ],
            return_route: null,
            summary: {
              estimated_duration_min: 510,
              dominant_transport_modes: ["步行", "公共交通"],
              estimated_walk_distance_m: 4800,
            },
          },
        ],
        lodging_recommendations: [
          {
            area_id: "map:wangfujing",
            name: "东单—王府井地铁站周边",
            level: "首选",
            representative_station: "王府井站",
            reason: "前往故宫交通方便，餐饮和地铁选择集中。",
            covered_attractions: ["故宫博物院"],
            avg_transit_min: 20,
          },
        ],
        limitations: [],
        validation: { status: "pass", checks: [], checked_at: "2026-08-22T08:03:00Z" },
        planner: { model: "deepseek-chat", model_version: "2026-08", prompt_version: "planner-v1.2" },
        generated_at: "2026-08-22T08:03:00Z",
      },
      retrieval_run_ids: [],
      knowledge_index_version: "beijing-photo-spot-v1",
      created_at: "2026-08-22T08:03:00Z",
    },
  };

  await page.addInitScript(() => window.localStorage.setItem("picpal_invited", "1"));
  await page.route("**/api/v1/conversations?limit=30", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: [], meta: { has_next: false, next_cursor: null } }),
    }),
  );
  await page.route("**/api/v1/conversations/conv-mobile-result", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ data: snapshot }),
    }),
  );
}

test("welcome workspace is ready for a travel request", async ({ page }, testInfo) => {
  await mockEmptyHistory(page);
  await page.goto("/plan");

  await expect(page.getByRole("heading", { name: "从想去的地方开始" })).toBeVisible();
  if (testInfo.project.name.startsWith("mobile")) {
    await expect(page.getByRole("button", { name: "查看历史对话" })).toBeVisible();
  } else {
    await expect(page.getByRole("heading", { name: "历史对话" })).toBeVisible();
  }

  const composer = page.getByRole("textbox", { name: "描述你的旅行计划" });
  const send = page.getByRole("button", { name: "发送旅行需求" });
  await expect(send).toBeDisabled();

  await page.getByRole("button", { name: /首次到访/ }).click();
  await expect(composer).toHaveValue(/北京/);
  await expect(send).toBeEnabled();
});

test("homepage preference is prefilled in the protected planner", async ({ page }) => {
  await mockEmptyHistory(page);
  const prompt = "带父母去北京玩三天，希望少走路、节奏轻松，也想留几张好看的合照。";

  await page.goto(`/plan?prompt=${encodeURIComponent(prompt)}`);

  await expect(page.getByRole("textbox", { name: "描述你的旅行计划" })).toHaveValue(prompt);
  await expect(page.getByRole("button", { name: "发送旅行需求" })).toBeEnabled();
});

test("mobile history opens as a drawer without squeezing the workspace", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile"), "mobile-only behavior");
  await mockEmptyHistory(page);
  await page.goto("/plan");

  const historyButton = page.getByRole("button", { name: "查看历史对话" });
  await expect(historyButton).toBeVisible();
  await historyButton.click();

  await expect(page.getByRole("complementary", { name: "旅行计划导航" })).toHaveClass(/sidebar-open/);
  await expect(page.getByText("还没有旅行计划")).toBeVisible();
});

test("mobile completed route uses the full viewport with readable type", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile"), "mobile-only behavior");
  await mockCompletedConversation(page);
  await page.goto("/chat/conv-mobile-result");

  const shell = page.locator(".app-shell.has-result");
  const mobilePlan = page.locator(".mobile-result-copy");
  await expect(shell).toBeVisible();
  await expect(mobilePlan.getByRole("heading", { name: "北京经典与城市漫游 1 日" })).toBeVisible();
  await expect(page.locator(".app-shell.has-result > .result-panel")).toBeHidden();

  const metrics = await page.evaluate(() => {
    const shellElement = document.querySelector<HTMLElement>(".app-shell.has-result");
    const userBubble = document.querySelector<HTMLElement>(".user-bubble");
    const itineraryTitle = document.querySelector<HTMLElement>(".mobile-result-copy .itinerary-header h2");
    return {
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      shellWidth: shellElement?.getBoundingClientRect().width ?? 0,
      userFontSize: Number.parseFloat(getComputedStyle(userBubble!).fontSize),
      itineraryTitleFontSize: Number.parseFloat(getComputedStyle(itineraryTitle!).fontSize),
    };
  });

  expect(metrics.documentWidth).toBe(metrics.viewportWidth);
  expect(metrics.shellWidth).toBe(metrics.viewportWidth);
  expect(metrics.userFontSize).toBeGreaterThanOrEqual(16);
  expect(metrics.itineraryTitleFontSize).toBeGreaterThanOrEqual(24);
});
