<template>
  <main class="placeholder">
    <h1>Dodgeball</h1>
    <!-- Placeholder: create room / join by code / screen-or-phone choice. -->
    <nav>
      <RouterLink to="/lobby">Lobby</RouterLink>
      <RouterLink to="/screen">Screen</RouterLink>
      <RouterLink to="/phone">Phone</RouterLink>
      <RouterLink to="/sensors">Sensor playground</RouterLink>
    </nav>
  </main>
</template>

<style scoped>
.placeholder {
  padding: 2rem;
}
nav {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
a {
  color: #8cf;
}
</style>
