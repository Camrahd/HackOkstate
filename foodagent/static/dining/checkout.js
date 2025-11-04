function getCsrfToken() {
  const m = document.cookie.match(/csrftoken=([^;]+)/);
  return m ? m[1] : '';
}

async function reverseGeocode(lat, lng) {
  const res = await fetch(`/api/reverse-geocode?lat=${lat}&lng=${lng}`, {
    headers: { 'X-CSRFToken': getCsrfToken() }
  });
  if (!res.ok) throw new Error('Reverse geocode failed');
  return await res.json(); // { address_line1, address_line2, city, state, postal_code }
}

async function fillFromGPS() {
  return new Promise((resolve, reject) => {
    if (!('geolocation' in navigator)) {
      reject(new Error('Geolocation not supported'));
      return;
    }
    navigator.geolocation.getCurrentPosition(async pos => {
      try {
        const { latitude: lat, longitude: lng } = pos.coords;
        document.getElementById('lat').value = lat;
        document.getElementById('lng').value = lng;

        const data = await reverseGeocode(lat, lng);
        if (data.address_line1) document.getElementById('addr1').value = data.address_line1;
        document.getElementById('addr2').value = data.address_line2 || '';
        if (data.city)          document.getElementById('city').value  = data.city;
        if (data.state)         document.getElementById('state').value = data.state;
        if (data.postal_code)   document.getElementById('zip').value   = data.postal_code;

        resolve();
      } catch (e) {
        reject(e);
      }
    }, err => reject(err), { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 });
  });
}

// Wire up buttons (only if they exist on this page)
document.getElementById('deliveryBtn')?.addEventListener('click', async () => {
  try { await fillFromGPS(); } catch (e) { console.warn(e.message); }
});
document.getElementById('useLocation')?.addEventListener('click', async () => {
  try { await fillFromGPS(); } catch (e) { alert('Could not get your location. Please allow location access or fill address manually.'); }
});
