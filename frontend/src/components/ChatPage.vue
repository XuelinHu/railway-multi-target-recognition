<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { Loader2, MessageSquare, Plus, Send, Square, Volume2 } from "@lucide/vue";
import {
  type ChatLanguage,
  type ChatMessage,
  type ChatModelInfo,
  ApiRequestError,
  fetchSpeech,
  listChatModels,
  streamChatCompletion,
} from "../api";

const props = defineProps<{ username: string }>();

const messages = ref<ChatMessage[]>([]);
const draft = ref("");
const streaming = ref(false);
const streamError = ref("");
const models = ref<ChatModelInfo[]>([]);
const model = ref("");
const lang = ref<ChatLanguage>("zh");
const autoSpeak = ref(false);
const speakingIndex = ref(-1);
const serviceWarning = ref("");
const messageListEl = ref<HTMLElement | null>(null);

let abortController: AbortController | null = null;
let audio: HTMLAudioElement | null = null;
let audioUrl = "";

const storageKey = (suffix: string) => `chat:${suffix}:${props.username}`;
const canSend = computed(() => draft.value.trim().length > 0 && !streaming.value);

onMounted(() => {
  lang.value = readStored(storageKey("lang"), "zh") === "en" ? "en" : "zh";
  autoSpeak.value = readStored(storageKey("autoSpeak"), "0") === "1";
  model.value = readStored(storageKey("model"), "");
  messages.value = readHistory();
  void scrollToBottom();
  void loadModels();
});

onBeforeUnmount(() => {
  abortController?.abort();
  stopAudio();
});

function readStored(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeStored(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage may be unavailable; the chat still works without persistence */
  }
}

function readHistory(): ChatMessage[] {
  try {
    const raw = localStorage.getItem(storageKey("history"));
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is ChatMessage => typeof item?.role === "string" && typeof item?.content === "string")
      .slice(-40);
  } catch {
    return [];
  }
}

function persistHistory(): void {
  writeStored(storageKey("history"), JSON.stringify(messages.value.slice(-40)));
}

async function loadModels(): Promise<void> {
  try {
    const data = await listChatModels();
    models.value = data.models;
    if (!model.value || !data.models.some((item) => item.name === model.value)) {
      model.value = data.defaultModel || data.models[0]?.name || "";
    }
    serviceWarning.value = "";
  } catch (error) {
    serviceWarning.value = error instanceof Error ? error.message : "无法获取本地模型列表";
  }
}

function onModelChange(): void {
  writeStored(storageKey("model"), model.value);
}

function toggleLang(): void {
  lang.value = lang.value === "zh" ? "en" : "zh";
  writeStored(storageKey("lang"), lang.value);
}

function toggleAutoSpeak(): void {
  autoSpeak.value = !autoSpeak.value;
  writeStored(storageKey("autoSpeak"), autoSpeak.value ? "1" : "0");
}

function newChat(): void {
  if (streaming.value) return;
  messages.value = [];
  streamError.value = "";
  persistHistory();
}

async function send(): Promise<void> {
  const text = draft.value.trim();
  if (!text || streaming.value) return;

  messages.value.push({ role: "user", content: text });
  draft.value = "";
  streamError.value = "";
  streaming.value = true;
  messages.value.push({ role: "assistant", content: "" });
  const assistantIndex = messages.value.length - 1;
  void scrollToBottom();

  abortController = new AbortController();
  try {
    await streamChatCompletion(
      {
        messages: messages.value
          .slice(0, assistantIndex)
          .filter((item) => item.role !== "system")
          .slice(-30),
        model: model.value || undefined,
        lang: lang.value,
      },
      {
        onDelta: (chunk) => {
          messages.value[assistantIndex].content += chunk;
          void scrollToBottom();
        },
        onDone: () => {
          void finishStream(assistantIndex);
        },
        onError: (detail) => {
          streamError.value = detail;
          messages.value[assistantIndex].content ||= `⚠ ${detail}`;
        },
      },
      abortController.signal,
    );
  } catch (error) {
    if ((error as Error)?.name === "AbortError") {
      if (!messages.value[assistantIndex].content) messages.value[assistantIndex].content = "（已停止）";
    } else {
      const detail = error instanceof ApiRequestError || error instanceof Error ? error.message : "对话失败";
      streamError.value = detail;
      messages.value[assistantIndex].content ||= `⚠ ${detail}`;
    }
  } finally {
    abortController = null;
    streaming.value = false;
    persistHistory();
  }
}

async function finishStream(assistantIndex: number): Promise<void> {
  persistHistory();
  const content = messages.value[assistantIndex]?.content ?? "";
  if (autoSpeak.value && content && !content.startsWith("⚠")) {
    await speak(assistantIndex, content);
  }
}

function stop(): void {
  abortController?.abort();
}

async function scrollToBottom(): Promise<void> {
  await nextTick();
  const element = messageListEl.value;
  if (element) element.scrollTop = element.scrollHeight;
}

async function speak(index: number, text: string): Promise<void> {
  if (!text.trim()) return;
  stopAudio();
  try {
    const blob = await fetchSpeech(text, lang.value);
    audioUrl = URL.createObjectURL(blob);
    audio = new Audio(audioUrl);
    speakingIndex.value = index;
    audio.onended = () => {
      speakingIndex.value = -1;
      releaseAudioUrl();
    };
    audio.onerror = () => {
      speakingIndex.value = -1;
      releaseAudioUrl();
    };
    await audio.play();
  } catch (error) {
    speakingIndex.value = -1;
    releaseAudioUrl();
    streamError.value = error instanceof Error ? error.message : "语音合成失败";
  }
}

function stopAudio(): void {
  if (audio) {
    audio.pause();
    audio = null;
  }
  speakingIndex.value = -1;
  releaseAudioUrl();
}

function releaseAudioUrl(): void {
  if (audioUrl) {
    URL.revokeObjectURL(audioUrl);
    audioUrl = "";
  }
}

function formatBytes(size: number): string {
  if (!size) return "";
  return `${(size / 1024 / 1024 / 1024).toFixed(1)}GB`;
}
</script>

<template>
  <section class="chat-page">
    <header class="chat-toolbar">
      <div class="chat-title">
        <MessageSquare :size="20" />
        <div>
          <h2>本地大模型对话</h2>
          <p>{{ serviceWarning || "基于本机 Ollama，支持中英双语与语音朗读" }}</p>
        </div>
      </div>
      <div class="chat-actions">
        <label class="chat-field">
          <span>模型</span>
          <select v-model="model" :disabled="streaming" @change="onModelChange">
            <option v-if="models.length === 0" value="">{{ model || "未检测到模型" }}</option>
            <option v-for="item in models" :key="item.name" :value="item.name">
              {{ item.name }}{{ item.size ? ` · ${formatBytes(item.size)}` : "" }}
            </option>
          </select>
        </label>
        <button :class="{ active: lang === 'en' }" :title="lang === 'zh' ? '当前中文，点击切换英文' : 'Current English, click for Chinese'" @click="toggleLang">
          {{ lang === "zh" ? "中文" : "EN" }}
        </button>
        <button :class="{ active: autoSpeak }" title="自动朗读回复" @click="toggleAutoSpeak">
          <Volume2 :size="16" />自动朗读
        </button>
        <button :disabled="streaming || messages.length === 0" title="开始新对话" @click="newChat">
          <Plus :size="16" />新对话
        </button>
      </div>
    </header>

    <div ref="messageListEl" class="chat-messages">
      <div v-if="messages.length === 0" class="empty-state chat-empty">
        向本地模型提问铁路巡检、接触网、轨道或施工安全相关问题，中英文均可。
      </div>
      <article
        v-for="(item, index) in messages"
        :key="index"
        class="chat-bubble"
        :class="item.role === 'user' ? 'from-user' : 'from-assistant'"
      >
        <div class="chat-bubble-head">
          <strong>{{ item.role === "user" ? "我" : "本地模型" }}</strong>
          <button
            v-if="item.role === 'assistant' && item.content"
            class="chat-speak"
            :class="{ active: speakingIndex === index }"
            title="朗读这条回复"
            @click="speak(index, item.content)"
          >
            <Loader2 v-if="speakingIndex === index" class="spin" :size="14" />
            <Volume2 v-else :size="14" />
          </button>
        </div>
        <p class="chat-text">{{ item.content || (streaming && index === messages.length - 1 ? "…" : "") }}</p>
      </article>
    </div>

    <footer class="chat-input-row">
      <textarea
        v-model="draft"
        rows="2"
        :placeholder="lang === 'zh' ? '输入问题，Enter 发送，Shift+Enter 换行' : 'Ask a question. Enter to send, Shift+Enter for a new line.'"
        @keydown.enter.exact.prevent="send"
      ></textarea>
      <button v-if="streaming" class="danger-button" @click="stop"><Square :size="16" />停止</button>
      <button v-else :disabled="!canSend" @click="send"><Send :size="16" />发送</button>
    </footer>
  </section>
</template>
