"use client";

import { ArrowUp, Image as ImageIcon, LoaderCircle, Mic } from "lucide-react";
import { ChangeEvent, FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";

type ChatComposerProps = {
  value?: string;
  onValueChange?: (value: string) => void;
  onSubmit: (value: string) => boolean | void | Promise<boolean | void>;
  disabled?: boolean;
  placeholder?: string;
  animatePlaceholder?: boolean;
};

export function ChatComposer({
  value,
  onValueChange,
  onSubmit,
  disabled = false,
  placeholder = "例如：第一次去北京，想看经典景点和胡同，每天别太赶……",
  animatePlaceholder = false,
}: ChatComposerProps) {
  const [internalValue, setInternalValue] = useState("");
  const [selectedImageName, setSelectedImageName] = useState("");
  const [listening, setListening] = useState(false);
  const uploadInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const currentValue = value ?? internalValue;
  const canSubmit = currentValue.trim().length > 0 && !disabled;

  useEffect(() => {
    if (!animatePlaceholder) return;

    const textarea = textareaRef.current;
    if (!textarea) return;

    const placeholderTexts = [
      "例如：第一次去北京，想看经典景点和胡同，每天别太赶……",
      "例如：周末去北京，喜欢胡同、展览和城市夜景……",
    ];

    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let textIndex = 0;
    let characterIndex = 0;
    let state: "typing" | "holding" | "erasing" = "typing";
    let timer: number | null = null;

    const runPlaceholderAnimation = () => {
      if (reduceMotion) {
        textarea.placeholder = placeholderTexts[0];
        return;
      }

      // 用户已经输入内容时暂停
      if (textarea.value.trim()) {
        timer = window.setTimeout(runPlaceholderAnimation, 500);
        return;
      }

      const currentText = placeholderTexts[textIndex];

      if (state === "typing") {
        characterIndex += 1;
        textarea.placeholder = currentText.slice(0, characterIndex);

        if (characterIndex >= currentText.length) {
          state = "holding";
          timer = window.setTimeout(runPlaceholderAnimation, 4000);
        } else {
          timer = window.setTimeout(runPlaceholderAnimation, 50);
        }
        return;
      }

      if (state === "holding") {
        state = "erasing";
        timer = window.setTimeout(runPlaceholderAnimation, 15);
        return;
      }

      characterIndex -= 1;
      textarea.placeholder = currentText.slice(0, Math.max(characterIndex, 0));

      if (characterIndex <= 0) {
        textIndex = (textIndex + 1) % placeholderTexts.length;
        state = "typing";
        timer = window.setTimeout(runPlaceholderAnimation, 400);
      } else {
        timer = window.setTimeout(runPlaceholderAnimation, 15);
      }
    };

    timer = window.setTimeout(runPlaceholderAnimation, 50);

    return () => {
      if (timer !== null) window.clearTimeout(timer);
    };
  }, [animatePlaceholder]);

  function updateValue(nextValue: string) {
    if (value === undefined) setInternalValue(nextValue);
    onValueChange?.(nextValue);
  }

  async function submit() {
    const content = currentValue.trim();
    if (!content || disabled) return;
    const accepted = await onSubmit(content);
    if (accepted !== false) updateValue("");
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  }

  function handleImageChange(event: ChangeEvent<HTMLInputElement>) {
    setSelectedImageName(event.target.files?.[0]?.name ?? "");
  }

  return (
    <form className={`composer ${listening ? "is-listening" : ""}`} onSubmit={handleSubmit} aria-busy={disabled}>
      <label className="sr-only" htmlFor="travel-prompt">
        描述你的旅行计划
      </label>
      <textarea
        ref={textareaRef}
        id="travel-prompt"
        name="travel-prompt"
        rows={2}
        maxLength={4000}
        value={currentValue}
        onChange={(event) => updateValue(event.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
      />
      <div className="composer-footer">
        <div className="composer-input-note">
          <button
            className="upload-image"
            type="button"
            disabled={disabled || listening}
            aria-label={selectedImageName ? `已选择图片：${selectedImageName}` : "上传图片"}
            onClick={() => uploadInputRef.current?.click()}
          >
            <ImageIcon aria-hidden="true" size={15} />
            <span>{selectedImageName || "上传图片"}</span>
          </button>
          <input
            ref={uploadInputRef}
            className="upload-input"
            type="file"
            accept="image/*"
            disabled={disabled}
            onChange={handleImageChange}
          />
          <span className="voice-wave" aria-hidden="true"><i /><i /><i /></span>
          <span className="listening-label" aria-live="polite">正在聆听…</span>
        </div>
        <div className="composer-actions">
          <button
            className="voice-button"
            type="button"
            disabled={disabled}
            aria-label={listening ? "停止语音输入" : "语音输入"}
            aria-pressed={listening}
            onClick={() => setListening((active) => !active)}
          >
            <Mic aria-hidden="true" size={18} />
          </button>
          <button
            className="send-button"
            type="submit"
            disabled={!canSubmit}
            aria-label={disabled ? "正在发送旅行需求" : "发送旅行需求"}
          >
            {disabled ? (
              <LoaderCircle className="send-spinner" aria-hidden="true" size={19} />
            ) : (
              <ArrowUp aria-hidden="true" size={20} strokeWidth={2.2} />
            )}
          </button>
        </div>
      </div>
    </form>
  );
}
