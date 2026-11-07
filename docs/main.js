(() => {
  var LANGS = ["en", "ja", "zh-CN", "zh-TW", "es", "ru", "de"];
  var META = {
    en: {
      title: "misskey-drive-downloader — Back up your meiV11 drive",
      description: "Download every file in your Misskey (meiV11) drive, keeping the folder structure. Python standard library only, resumable, with automatic retries.",
      themeLabel: "Toggle color theme"
    },
    ja: {
      title: "misskey-drive-downloader — meiV11 のドライブをまるごとバックアップ",
      description: "Misskey（meiV11）のドライブにある全ファイルを、フォルダー構造を保ったままダウンロード。Python 標準ライブラリーのみ、中断からの再開と自動リトライに対応。",
      themeLabel: "カラーテーマを切り替え"
    },
    "zh-CN": {
      title: "misskey-drive-downloader — 备份你的 meiV11 网盘",
      description: "保持文件夹结构，下载 Misskey（meiV11）网盘中的全部文件。仅使用 Python 标准库，支持断点续传和自动重试。",
      themeLabel: "切换颜色主题"
    },
    "zh-TW": {
      title: "misskey-drive-downloader — 備份你的 meiV11 雲端硬碟",
      description: "保留資料夾結構，下載 Misskey（meiV11）雲端硬碟中的所有檔案。僅使用 Python 標準函式庫，支援中斷續傳與自動重試。",
      themeLabel: "切換色彩主題"
    },
    es: {
      title: "misskey-drive-downloader — Copia de seguridad de tu Drive de meiV11",
      description: "Descarga todos los archivos de tu Drive de Misskey (meiV11) conservando la estructura de carpetas. Solo usa la biblioteca estándar de Python, se puede reanudar y reintenta automáticamente.",
      themeLabel: "Cambiar tema de color"
    },
    ru: {
      title: "misskey-drive-downloader — Резервная копия вашего Диска meiV11",
      description: "Скачивает все файлы с Диска Misskey (meiV11) с сохранением структуры папок. Только стандартная библиотека Python, возобновление загрузки и автоматические повторы.",
      themeLabel: "Переключить цветовую тему"
    },
    de: {
      title: "misskey-drive-downloader — Sichere dein meiV11-Drive",
      description: "Lädt alle Dateien aus deinem Misskey-Drive (meiV11) herunter und behält die Ordnerstruktur bei. Nur Python-Standardbibliothek, fortsetzbar, mit automatischen Wiederholungen.",
      themeLabel: "Farbschema wechseln"
    }
  };

  var root = document.documentElement;

  function storageGet(key) {
    try { return localStorage.getItem(key); } catch (_) { return null; }
  }

  function storageSet(key, value) {
    try { localStorage.setItem(key, value); } catch (_) {}
  }

  // Language
  var ml = new MultilanguageJS({ languages: LANGS, defaultLanguage: "en" });
  var langSelect = document.getElementById("lang-select");
  var themeToggle = document.getElementById("theme-toggle");

  function applyMeta(lang) {
    var m = META[lang] || META.en;
    document.title = m.title;
    var desc = document.querySelector('meta[name="description"]');
    if (desc) desc.setAttribute("content", m.description);
    if (themeToggle) themeToggle.setAttribute("aria-label", m.themeLabel);
  }

  // ブラウザの言語 (例: zh-Hant-TW, zh-HK, de-AT) を対応言語へ寄せる
  function detectLanguage() {
    var langs = navigator.languages && navigator.languages.length ? navigator.languages : [navigator.language || "en"];
    for (var i = 0; i < langs.length; i++) {
      var tag = langs[i].toLowerCase();
      if (tag.indexOf("zh") === 0) {
        return /hant|tw|hk|mo/.test(tag) ? "zh-TW" : "zh-CN";
      }
      var base = tag.split("-")[0];
      if (LANGS.indexOf(base) !== -1) return base;
    }
    return "en";
  }

  function setLanguage(lang) {
    if (LANGS.indexOf(lang) === -1) lang = "en";
    ml.setLanguage(lang);
    applyMeta(lang);
    root.setAttribute("lang", lang);
    if (langSelect) langSelect.value = lang;
    storageSet("lang", lang);
  }

  setLanguage(storageGet("lang") || detectLanguage());

  if (langSelect) {
    langSelect.addEventListener("change", (e) => setLanguage(e.target.value));
  }

  // Theme: 現在のテーマ (保存済み、なければ OS 設定) の反対へ切り替えて保存する
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      var current = root.dataset.theme
        || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var next = current === "dark" ? "light" : "dark";
      root.dataset.theme = next;
      storageSet("theme", next);
    });
  }
})();
