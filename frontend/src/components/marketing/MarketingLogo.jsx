import { Link } from "react-router-dom";
import { CATEGORY } from "@/lib/marketingCopy";
import trenstonMark from "@/assets/trenston-mark.svg";
import trenstonMarkNavy from "@/assets/trenston-mark-navy.svg";
import trenstonWordmarkNavy from "@/assets/trenston-wordmark-navy.svg";
import trenstonWordmarkCream from "@/assets/trenston-wordmark-cream.svg";

/** Clickable Trenston mark — always routes to the marketing home page. */
export default function MarketingLogo({
  size = "md",
  showTagline = false,
  className = "",
  dark = false,
  variant = "icon",
}) {
  const box = size === "sm" ? "w-7 h-7" : "w-9 h-9";
  const name = size === "sm" ? "text-sm" : "text-base";
  const iconPx = size === "sm" ? 28 : 36;
  const wordmarkH = size === "sm" ? 18 : 22;
  const markSrc = dark ? trenstonMarkNavy : trenstonMark;
  const wordmarkSrc = dark ? trenstonWordmarkCream : trenstonWordmarkNavy;

  const markImg = (
    <img
      src={markSrc}
      alt=""
      width={iconPx}
      height={iconPx}
      className={`${box} shrink-0 rounded-md`}
      draggable={false}
    />
  );

  const wordmarkImg = (
    <img
      src={wordmarkSrc}
      alt="Trenston"
      height={wordmarkH}
      className="shrink-0"
      style={{ height: wordmarkH, width: "auto" }}
      draggable={false}
    />
  );

  let body;
  if (variant === "wordmark") {
    body = (
      <div>
        {wordmarkImg}
        {showTagline && (
          <p className={`text-[10px] font-mono uppercase tracking-[0.2em] mt-1 ${dark ? "text-helm-slate" : "text-helm-slate"}`}>{CATEGORY}</p>
        )}
      </div>
    );
  } else if (variant === "lockup") {
    body = (
      <>
        {markImg}
        <div>
          {wordmarkImg}
          {showTagline && (
            <p className={`text-[10px] font-mono uppercase tracking-[0.2em] mt-1 ${dark ? "text-helm-slate" : "text-helm-slate"}`}>{CATEGORY}</p>
          )}
        </div>
      </>
    );
  } else {
    // variant === "icon" — preserve existing markup/classes exactly
    body = (
      <>
        {markImg}
        <div>
          <p className={`font-semibold tracking-tight leading-none ${name} ${dark ? "text-helm-cream" : "text-helm-navy"}`}>Trenston</p>
          {showTagline && (
            <p className={`text-[10px] font-mono uppercase tracking-[0.2em] mt-1 ${dark ? "text-helm-slate" : "text-helm-slate"}`}>{CATEGORY}</p>
          )}
        </div>
      </>
    );
  }

  return (
    <Link
      to="/"
      className={`inline-flex items-center gap-2.5 group transition-opacity hover:opacity-90 ${className}`}
      data-testid="helm-logo-home"
    >
      {body}
    </Link>
  );
}
