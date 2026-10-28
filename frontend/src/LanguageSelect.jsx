import { t, useLocale } from "./i18n.js";

export default function LanguageSelect({ onChange, className = "" }) {
  const [locale, setLocale] = useLocale();
  return (
    <label className={`language-select ${className}`}>
      <span className="sr-only">{t("Язык интерфейса")}</span>
      <select
        aria-label={t("Язык интерфейса")}
        value={locale}
        onChange={(event) => {
          setLocale(event.target.value);
          onChange?.(event.target.value);
        }}
      >
        <option value="ru" lang="ru">Русский</option>
        <option value="en" lang="en">English</option>
      </select>
    </label>
  );
}
