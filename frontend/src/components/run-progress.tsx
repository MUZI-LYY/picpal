import type { Run } from "@/lib/conversation-api";

type RunProgressProps = {
  run: Run;
};

const stageFallbacks: Record<Run["stages"][number]["key"], string> = {
  understanding_request: "理解旅行需求",
  resolving_pois: "确认景点与位置",
  planning_routes: "规划每日路线",
  recommending_lodging: "生成住宿建议",
  retrieving_photo_spots: "匹配真实出片点",
  validating: "检查时间与约束",
};

export const PROGRESS_STAGE_KEYS = [
  "understanding_request",
  "resolving_pois",
  "planning_routes",
  "recommending_lodging",
  "retrieving_photo_spots",
  "validating",
] as const;

export function RunProgress({ run }: RunProgressProps) {
  const heading =
    run.status === "failed"
      ? "这次规划没有完成"
      : run.status === "succeeded"
        ? "行程已生成"
        : "正在为你规划行程";

  return (
    <section className="run-progress" aria-labelledby="run-progress-title">
      <div className="run-heading">
        <h2 id="run-progress-title">{heading}</h2>
        <span>{run.status === "succeeded" ? "每一步都已完成" : "展示真实执行阶段，不使用百分比"}</span>
      </div>
      <ol className="stage-list">
        {run.stages.map((stage, index) => {
          const status =
            run.status === "queued" && index === 0
              ? "running"
              : run.status === "succeeded"
                ? "succeeded"
                : stage.status;
          const label = stage.label || stageFallbacks[stage.key];
          return (
            <li className={`stage stage-${status}`} key={stage.key}>
              <span className="stage-icon" aria-hidden="true">
                {status === "succeeded" ? "✓" : status === "running" ? "•" : status === "failed" ? "!" : "·"}
              </span>
              <span>{status === "succeeded" ? label : `正在${label}`}</span>
              <span className="stage-state">
                {status === "succeeded" ? "已完成" : status === "running" ? "进行中" : status === "failed" ? "失败" : "等待"}
              </span>
            </li>
          );
        })}
      </ol>
      {run.error ? <p className="run-error">{run.error.message}</p> : null}
    </section>
  );
}
