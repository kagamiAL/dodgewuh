<template>
  <main class="placeholder">
    <p>This page hasn't been merged yet.</p>
    <RouterLink to="/">Home</RouterLink>
  </main>
</template>

<style scoped>
.placeholder {
  padding: 2rem max(1rem, env(safe-area-inset-right)) 2rem max(1rem, env(safe-area-inset-left));
  overflow-wrap: break-word;
}
.placeholder a {
  display: inline-block;
  padding: 0.5rem 0;
  color: #8cf;
}
</style>
