"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ArrowUpRight, ChevronDown, MapPin } from "lucide-react";
import styles from "@/app/page.module.css";

const dayOptions = ["1", "2", "3", "4", "5"] as const;
const photoOptions = ["经典建筑", "胡同夜景", "湖光园林", "城市夜景", "人物合照"] as const;

export function TripStarter() {
  const router = useRouter();
  const [days, setDays] = useState<(typeof dayOptions)[number]>("3");
  const [photoPreference, setPhotoPreference] =
    useState<(typeof photoOptions)[number]>("经典建筑");

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const prompt = `我想去北京玩${days}天，节奏轻松一些，喜欢${photoPreference}，也想沿途拍到好看的照片。`;
    router.push(`/plan?prompt=${encodeURIComponent(prompt)}`);
  }

  return (
    <form className={styles.tripStarter} onSubmit={submit} aria-label="快速开始规划">
      <div className={styles.fixedField}>
        <span>目的地</span>
        <strong><MapPin size={14} aria-hidden="true" /> 北京</strong>
      </div>

      <label>
        <span>行程天数</span>
        <span className={styles.selectWrap}>
          <select value={days} onChange={(event) => setDays(event.target.value as typeof days)}>
            {dayOptions.map((day) => <option key={day} value={day}>{day} 天</option>)}
          </select>
          <ChevronDown size={13} aria-hidden="true" />
        </span>
      </label>

      <label>
        <span>想拍什么</span>
        <span className={styles.selectWrap}>
          <select
            value={photoPreference}
            onChange={(event) => setPhotoPreference(event.target.value as typeof photoPreference)}
          >
            {photoOptions.map((option) => <option key={option} value={option}>{option}</option>)}
          </select>
          <ChevronDown size={13} aria-hidden="true" />
        </span>
      </label>

      <button type="submit" aria-label={`按北京 ${days} 天、${photoPreference}开始规划`}>
        <ArrowUpRight size={20} aria-hidden="true" />
      </button>
    </form>
  );
}
