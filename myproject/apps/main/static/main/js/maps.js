/*
 * RescueBite Design System - donor pickup maps.
 * Each claimed donation renders one small map showing donor -> NGO.
 * Configured entirely from data attributes on the map container.
 */
(function () {
    'use strict';

    function number(value) {
        var parsed = parseFloat(value);
        return isNaN(parsed) ? null : parsed;
    }

    function init() {
        if (typeof L === 'undefined') {
            return;
        }

        document.querySelectorAll('[data-rb-map]').forEach(function (el) {
            var donor = [number(el.dataset.donorLat), number(el.dataset.donorLng)];
            var ngo = [number(el.dataset.ngoLat), number(el.dataset.ngoLng)];

            if (donor[0] === null || ngo[0] === null) {
                return;
            }

            try {
                var map = L.map(el).setView(donor, 13);
                L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                    attribution: '&copy; OpenStreetMap'
                }).addTo(map);

                L.marker(donor).addTo(map).bindPopup('Donation pickup location');
                L.marker(ngo).addTo(map).bindPopup(
                    'NGO: ' + (el.dataset.ngoName || '')
                );

                var line = L.polyline([donor, ngo], {
                    color: '#15803d',
                    weight: 4,
                    dashArray: '5, 10'
                }).addTo(map);

                map.fitBounds(line.getBounds(), { padding: [30, 30] });
                window.addEventListener('resize', function () {
                    map.invalidateSize();
                });
            } catch (error) {
                if (window.console && console.error) {
                    console.error(error);
                }
            }
        });
    }

    window.RescueBite = window.RescueBite || {};
    window.RescueBite.initDonorMaps = init;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
}());
