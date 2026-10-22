/**
 * Build de produção do Tailwind (substitui o CDN `cdn.tailwindcss.com`, que
 * compila no navegador a cada página). Gera apenas as classes usadas nos templates.
 *
 * Rebuild após mexer em classes dos templates:
 *   npx tailwindcss@3 -i assets/tailwind.src.css -o static/css/tailwind.build.css --minify
 */
module.exports = {
  content: ["./templates/**/*.html"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#F0F2F8",
          100: "#E4E8F4",
          200: "#CBD5F5",
          600: "#3F4AB7",
          700: "#343DA5",
          800: "#2B3291",
          900: "#222873",
          950: "#171B55",
        },
        action: {
          50: "#F0F6FF",
          100: "#E0ECFF",
          500: "#1769D2",
          600: "#0B57C5",
          700: "#0248AB",
          800: "#003682",
        },
        accentred: {
          50: "#FEF2F2",
          100: "#FEE2E2",
          500: "#E33A40",
          600: "#D12B32",
          700: "#B4232A",
          800: "#93191E",
        },
        govblue: {
          50: "#F0F2F8",
          100: "#E0ECFF",
          600: "#0B57C5",
          700: "#0248AB",
          800: "#222873",
          900: "#171B55",
        },
        status: {
          atende: "#16a34a",
          naoatende: "#dc2626",
          naoenviado: "#d97706",
          naoaplicavel: "#64748b",
          emanalise: "#0B57C5",
        },
      },
    },
  },
};
