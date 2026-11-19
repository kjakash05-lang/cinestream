/**
 * profile.js - CineStream Profile & Preferences Controller
 */
(function() {
  'use strict';

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  const AVATARS = [
    { id: 'avatar-1', label: 'Classic Cinephile', icon: '🎬' },
    { id: 'avatar-2', label: 'Sci-Fi Explorer', icon: '🚀' },
    { id: 'avatar-3', label: 'Golden Era Critic', icon: '🎭' },
    { id: 'avatar-4', label: 'Action Hero', icon: '⚡' },
    { id: 'avatar-5', label: 'Binge Watcher', icon: '🍿' },
    { id: 'avatar-6', label: 'Mystery Sleuth', icon: '🕵️' }
  ];

  const GENRES = [
    "Action", "Adventure", "Animation", "Comedy", "Crime", "Documentary",
    "Drama", "Family", "Fantasy", "History", "Horror", "Music",
    "Mystery", "Romance", "Science Fiction", "Thriller", "War", "Western"
  ];

  const LANGUAGES = [
    { code: "all", name: "All Languages" },
    { code: "en", name: "English" },
    { code: "hi", name: "Hindi" },
    { code: "kn", name: "Kannada" },
    { code: "ta", name: "Tamil" },
    { code: "te", name: "Telugu" },
    { code: "ml", name: "Malayalam" },
    { code: "ja", name: "Japanese" }
  ];

  let selectedAvatar = 'avatar-1';
  let selectedGenres = new Set();
  let selectedLanguages = new Set(['all']);

  const avatarGrid = document.getElementById('avatarGrid');
  const genrePills = document.getElementById('genrePills');
  const langPills = document.getElementById('langPills');
  const usernameField = document.getElementById('usernameField');
  const displayNameField = document.getElementById('displayNameField');
  const trailerAudioSelect = document.getElementById('trailerAudioSelect');
  const defaultTabSelect = document.getElementById('defaultTabSelect');
  const adultToggle = document.getElementById('adultToggle');
  const saveBtn = document.getElementById('savePreferencesBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const toastMsg = document.getElementById('toastMsg');

  // Delete modal elements
  const deleteBtn = document.getElementById('deleteAccountBtn');
  const deleteModal = document.getElementById('deleteModal');
  const confirmDeleteInput = document.getElementById('confirmDeleteInput');
  const confirmDeleteBtn = document.getElementById('confirmDeleteBtn');
  const cancelDeleteBtn = document.getElementById('cancelDeleteBtn');

  function showToast(text, duration = 3000) {
    if (!toastMsg) return;
    toastMsg.textContent = text;
    toastMsg.style.display = 'block';
    setTimeout(() => {
      toastMsg.style.display = 'none';
    }, duration);
  }

  function renderAvatars() {
    if (!avatarGrid) return;
    avatarGrid.innerHTML = AVATARS.map(a => `
      <div class="avatar-option ${a.id === selectedAvatar ? 'selected' : ''}" data-avatar="${a.id}">
        <div class="avatar-icon">${a.icon}</div>
        <div class="avatar-label">${a.label}</div>
      </div>
    `).join('');

    avatarGrid.querySelectorAll('.avatar-option').forEach(el => {
      el.addEventListener('click', () => {
        avatarGrid.querySelectorAll('.avatar-option').forEach(item => item.classList.remove('selected'));
        el.classList.add('selected');
        selectedAvatar = el.dataset.avatar;
      });
    });
  }

  function renderGenres() {
    if (!genrePills) return;
    genrePills.innerHTML = GENRES.map(g => `
      <button type="button" class="pill-btn ${selectedGenres.has(g) ? 'active' : ''}" data-genre="${g}">
        ${g}
      </button>
    `).join('');

    genrePills.querySelectorAll('.pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const g = btn.dataset.genre;
        if (selectedGenres.has(g)) {
          selectedGenres.delete(g);
          btn.classList.remove('active');
        } else {
          selectedGenres.add(g);
          btn.classList.add('active');
        }
      });
    });
  }

  function renderLanguages() {
    if (!langPills) return;
    langPills.innerHTML = LANGUAGES.map(l => `
      <button type="button" class="pill-btn ${selectedLanguages.has(l.code) ? 'active' : ''}" data-lang="${l.code}">
        ${l.name}
      </button>
    `).join('');

    langPills.querySelectorAll('.pill-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const lang = btn.dataset.lang;
        if (lang === 'all') {
          selectedLanguages.clear();
          selectedLanguages.add('all');
          langPills.querySelectorAll('.pill-btn').forEach(b => b.classList.toggle('active', b.dataset.lang === 'all'));
        } else {
          selectedLanguages.delete('all');
          if (selectedLanguages.has(lang)) {
            selectedLanguages.delete(lang);
            btn.classList.remove('active');
            if (selectedLanguages.size === 0) selectedLanguages.add('all');
          } else {
            selectedLanguages.add(lang);
            btn.classList.add('active');
          }
          // Update 'all' button
          const allBtn = langPills.querySelector('[data-lang="all"]');
          if (allBtn) allBtn.classList.toggle('active', selectedLanguages.has('all'));
        }
      });
    });
  }

  async function loadProfile() {
    try {
      const res = await fetch('/api/profile');
      if (res.status === 401) {
        window.location.href = '/login?next=/profile';
        return;
      }
      const data = await res.json();
      if (!data.success) return;

      const user = data.user || {};
      const prefs = data.preferences || {};

      if (usernameField) usernameField.value = user.username || '';
      if (displayNameField) displayNameField.value = prefs.display_name || user.display_name || '';

      selectedAvatar = prefs.avatar || 'avatar-1';
      selectedGenres = new Set(prefs.favorite_genres || []);
      selectedLanguages = new Set(prefs.preferred_languages || ['all']);

      if (trailerAudioSelect) trailerAudioSelect.value = prefs.preferred_audio_lang || 'en';
      if (defaultTabSelect) defaultTabSelect.value = (prefs.favorite_tabs && prefs.favorite_tabs[0]) || 'all';
      if (adultToggle) adultToggle.checked = !!prefs.adult_content;

      renderAvatars();
      renderGenres();
      renderLanguages();
    } catch (e) {
      console.error('Failed to load profile:', e);
    }
  }

  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      saveBtn.disabled = true;
      saveBtn.textContent = 'Saving...';

      const payload = {
        display_name: displayNameField.value.trim(),
        avatar: selectedAvatar,
        favorite_genres: Array.from(selectedGenres),
        preferred_languages: Array.from(selectedLanguages),
        preferred_audio_lang: trailerAudioSelect.value,
        favorite_tabs: [defaultTabSelect.value],
        adult_content: adultToggle.checked ? 1 : 0
      };

      try {
        const res = await fetch('/api/profile', {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (res.ok && result.success) {
          showToast('Preferences updated successfully!');
        } else {
          alert(result.error || 'Failed to update preferences.');
        }
      } catch (e) {
        alert('Network error saving preferences.');
      } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Changes';
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener('click', async () => {
      try {
        await fetch('/api/auth/logout', {
          method: 'POST',
          headers: { 'X-CSRFToken': csrfToken }
        });
        window.location.href = '/';
      } catch (e) {
        window.location.href = '/';
      }
    });
  }

  // Delete modal logic
  if (deleteBtn && deleteModal) {
    deleteBtn.addEventListener('click', () => {
      deleteModal.style.display = 'flex';
      confirmDeleteInput.value = '';
      confirmDeleteBtn.disabled = true;
      confirmDeleteBtn.style.opacity = '0.5';
    });

    cancelDeleteBtn.addEventListener('click', () => {
      deleteModal.style.display = 'none';
    });

    confirmDeleteInput.addEventListener('input', () => {
      const match = confirmDeleteInput.value.trim() === 'DELETE';
      confirmDeleteBtn.disabled = !match;
      confirmDeleteBtn.style.opacity = match ? '1' : '0.5';
    });

    confirmDeleteBtn.addEventListener('click', async () => {
      confirmDeleteBtn.disabled = true;
      confirmDeleteBtn.textContent = 'Deleting...';
      try {
        const res = await fetch('/api/profile', {
          method: 'DELETE',
          headers: { 'X-CSRFToken': csrfToken }
        });
        if (res.ok) {
          window.location.href = '/';
        } else {
          alert('Could not delete account.');
          confirmDeleteBtn.disabled = false;
          confirmDeleteBtn.textContent = 'Permanently Delete';
        }
      } catch (e) {
        alert('Error connecting to server.');
      }
    });
  }

  // Initial load
  loadProfile();
})();
