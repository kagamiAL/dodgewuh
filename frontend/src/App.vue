<template>
  <RouterView />
</template>

<style>
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
  background: #111;
  color: #eee;
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
