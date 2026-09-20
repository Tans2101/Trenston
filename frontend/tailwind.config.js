const { HELM_PALETTE, HELM_FLAGGED } = require("./src/design/helmTokens");

/** @type {import('tailwindcss').Config} */
module.exports = {
    darkMode: ["class"],
    content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      borderRadius: {
        lg: 'var(--radius)',
        md: 'calc(var(--radius) - 2px)',
        sm: 'calc(var(--radius) - 4px)'
      },
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
        display: ['Hedvig Letters Sans', 'DM Sans', 'system-ui', 'sans-serif'],
        'serif-display': ['Hedvig Letters Sans', 'DM Sans', 'system-ui', 'sans-serif'],
      },
      colors: {
        helm: {
          navy: HELM_PALETTE.navy,
          gold: HELM_PALETTE.gold,
          "gold-hover": HELM_FLAGGED.goldHover,
          ember: HELM_PALETTE.ember,
          "ember-hover": HELM_FLAGGED.emberHover,
          slate: HELM_PALETTE.slate,
          cream: HELM_PALETTE.cream,
          ink: HELM_FLAGGED.ink,
          "ink-card": HELM_FLAGGED.inkCard,
          "status-positive": HELM_FLAGGED.statusPositive,
          "status-negative": HELM_FLAGGED.statusNegative,
          "status-warning": HELM_FLAGGED.statusWarning,
          fg: "var(--helm-fg)",
          bg: "var(--helm-bg)",
          card: "var(--helm-card)",
          muted: "var(--helm-muted)",
          line: "var(--helm-line)",
        },
        gold: {
          DEFAULT: HELM_PALETTE.gold,
          hover: HELM_FLAGGED.goldHover,
          muted: "rgba(201,162,75,0.15)"
        },
        background: 'hsl(var(--background))',
        foreground: 'hsl(var(--foreground))',
        card: {
          DEFAULT: 'hsl(var(--card))',
          foreground: 'hsl(var(--card-foreground))'
        },
        popover: {
          DEFAULT: 'hsl(var(--popover))',
          foreground: 'hsl(var(--popover-foreground))'
        },
        primary: {
          DEFAULT: 'hsl(var(--primary))',
          foreground: 'hsl(var(--primary-foreground))'
        },
        secondary: {
          DEFAULT: 'hsl(var(--secondary))',
          foreground: 'hsl(var(--secondary-foreground))'
        },
        muted: {
          DEFAULT: 'hsl(var(--muted))',
          foreground: 'hsl(var(--muted-foreground))'
        },
        accent: {
          DEFAULT: 'hsl(var(--accent))',
          foreground: 'hsl(var(--accent-foreground))'
        },
        destructive: {
          DEFAULT: 'hsl(var(--destructive))',
          foreground: 'hsl(var(--destructive-foreground))'
        },
        border: 'hsl(var(--border))',
        input: 'hsl(var(--input))',
        ring: 'hsl(var(--ring))',
        chart: {
          '1': 'hsl(var(--chart-1))',
          '2': 'hsl(var(--chart-2))',
          '3': 'hsl(var(--chart-3))',
          '4': 'hsl(var(--chart-4))',
          '5': 'hsl(var(--chart-5))'
        }
      },
      keyframes: {
        'accordion-down': {
          from: {
            height: '0'
          },
          to: {
            height: 'var(--radix-accordion-content-height)'
          }
        },
        'accordion-up': {
          from: {
            height: 'var(--radix-accordion-content-height)'
          },
          to: {
            height: '0'
          }
        }
      },
      animation: {
        'accordion-down': 'accordion-down 0.2s ease-out',
        'accordion-up': 'accordion-up 0.2s ease-out'
      }
    }
  },
  plugins: [require("tailwindcss-animate")],
};
