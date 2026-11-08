<template>
  <RouterView />
</template>

<style>
@font-face {
  font-family: 'Barlow Condensed';
  src: url('/fonts/BarlowCondensed-BlackItalic.ttf') format('truetype');
  font-weight: 900;
  font-style: italic;
  font-display: swap;
}
:root {
  color-scheme: dark;
  --bg: #101820;
  --surface: #1c2935;
  --text: #fff5dc;
  --muted: #a9b5c7;
  --line: #3b485b;
  --blue: #80baff;
  --orange: #ff8c26;
  --danger: #ff9d9d;
}
::selection { background: #88bdff; color: #10151e; }
:focus-visible { outline: 2px solid var(--blue); outline-offset: 4px; }
button, input, select, textarea { font-family: inherit; }
button, a, input, label { -webkit-tap-highlight-color: transparent; }
button { touch-action: manipulation; }
input, textarea { caret-color: var(--blue); }
html { scrollbar-color: #526179 var(--bg); }
a { text-underline-offset: 0.2em; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; scroll-behavior: auto !important; }
}
*,
*::before,
*::after {
  box-sizing: border-box;
}
html,
body,
#app {
  margin: 0;
  height: 100%;
  font-family: system-ui, -apple-system, sans-serif;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
body {
  /* Keep text at the author's size when a phone is rotated to landscape. */
  -webkit-text-size-adjust: 100%;
  overflow-x: hidden;
  /* Players shake and swing the phone: a stray swipe must not pull-to-refresh
     and drop them out of the room mid-round. */
  overscroll-behavior: none;
}
/* Fonts below 16px make iOS Safari zoom the page when a control is focused. */
input,
select,
textarea {
  font-size: max(1rem, 16px);
}
</style>
