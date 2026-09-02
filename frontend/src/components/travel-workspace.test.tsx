import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ChatComposer } from "./chat-composer";
import { TravelWorkspace } from "./travel-workspace";

describe("TravelWorkspace", () => {
  it("presents the PicPal travel planning welcome state", () => {
    render(<TravelWorkspace />);

    expect(screen.getAllByRole("link", { name: "PicPal 首页" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: /从想.*去的地方开始/ })).toBeInTheDocument();
    expect(screen.getByText(/规划顺路的行程/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /首次到访/ })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "北京 · 出片灵感" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "描述你的旅行计划" })).toBeInTheDocument();
  });

  it("starts with a homepage preference ready to edit", () => {
    render(<TravelWorkspace initialDraft="想带父母轻松逛北京三天" />);

    expect(screen.getByRole("textbox", { name: "描述你的旅行计划" })).toHaveValue(
      "想带父母轻松逛北京三天",
    );
    expect(screen.getByRole("button", { name: "发送旅行需求" })).toBeEnabled();
  });

  it("exposes new-plan, history and mobile history controls", () => {
    render(<TravelWorkspace />);

    expect(screen.getByRole("link", { name: /新建旅行计划/ })).toHaveAttribute("href", "/plan");
    expect(screen.getByRole("heading", { name: "历史对话" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "查看历史对话" })).toBeInTheDocument();
    expect(screen.getByText("还没有旅行计划")).toBeInTheDocument();
  });

  it("matches the V2.3 composer actions", () => {
    render(<TravelWorkspace />);

    expect(screen.getByRole("button", { name: "上传图片" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "语音输入" })).toBeInTheDocument();
  });
});

describe("ChatComposer", () => {
  it("prevents blank submissions and sends trimmed content", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(<ChatComposer onSubmit={onSubmit} />);

    const textbox = screen.getByRole("textbox", { name: "描述你的旅行计划" });
    const submit = screen.getByRole("button", { name: "发送旅行需求" });

    expect(submit).toBeDisabled();
    await user.type(textbox, "  我想在北京玩三天，喜欢建筑摄影  ");
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(onSubmit).toHaveBeenCalledWith("我想在北京玩三天，喜欢建筑摄影");
    expect(textbox).toHaveValue("");
  });

  it("lets a suggestion fill the editable composer", async () => {
    const user = userEvent.setup();

    render(<TravelWorkspace />);
    await user.click(screen.getByRole("button", { name: /首次到访/ }));

    const textbox = screen.getByRole("textbox", { name: "描述你的旅行计划" });
    expect((textbox as HTMLTextAreaElement).value).toMatch(/北京/);
  });

  it("keeps the request editable when submission is rejected", async () => {
    const user = userEvent.setup();

    render(<ChatComposer onSubmit={() => false} />);
    const textbox = screen.getByRole("textbox", { name: "描述你的旅行计划" });
    await user.type(textbox, "北京两天建筑摄影");
    await user.click(screen.getByRole("button", { name: "发送旅行需求" }));

    expect(textbox).toHaveValue("北京两天建筑摄影");
  });

  it("shows an explicit pending state while the request is being sent", () => {
    render(<ChatComposer onSubmit={() => undefined} disabled />);

    expect(screen.getByRole("button", { name: "正在发送旅行需求" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "上传图片" })).toBeDisabled();
  });

  it("shows the listening state used by the V2.3 prototype", async () => {
    const user = userEvent.setup();
    render(<ChatComposer onSubmit={() => undefined} />);

    await user.click(screen.getByRole("button", { name: "语音输入" }));

    expect(screen.getByRole("button", { name: "停止语音输入" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("正在聆听…")).toBeInTheDocument();
  });
});

describe("submission feedback", () => {
  it("makes backend failures visible and tells the user the draft is preserved", () => {
    render(<TravelWorkspace error="匿名会话服务暂时不可用" />);

    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("发送失败");
    expect(alert).toHaveTextContent("输入内容已保留，请重新发送");
  });
});
