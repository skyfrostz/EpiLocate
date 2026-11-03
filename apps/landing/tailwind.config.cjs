/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        meutas: ['"Meutas Medium"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        jetbrains: ['"JetBrains Mono"', '"PingFang SC"', '"Microsoft YaHei"', 'sans-serif'],
        zhongsong: ['"STZhongsong"', '"华文中宋"', '"STSong"', '"Songti SC"', 'serif'],
      },
    },
  },
  plugins: [],
}
