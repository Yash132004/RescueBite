/*
 * RescueBite - volunteer dashboard behaviour.
 *
 * Draws delivery routes on a Leaflet map (Leaflet + Leaflet Routing Machine,
 * OSRM as the routing service) and accepts a delivery via AJAX.
 *
 * Preserved on purpose:
 *   - the `#map` element id and `.rb-map` class,
 *   - the `.task-item` hook carrying data-plat/plon/dlat/dlon/donor/ngo,
 *   - `L.Routing.osrmv1` against the OSRM service URL,
 *   - the accept request: POST, JSON, { food_id }, X-CSRFToken header,
 *   - removing the card once the server accepts.
 *
 * Everything else (loading states, error reporting, live counters, removing
 * the accepted route from the map) is presentation only.
 */
(function () {
    'use strict';

    var RB = window.RescueBite;
    var DEFAULT_CENTER = [22.3072, 73.1812];
    var ROUTE_COLOR = '#15803d';

    // Routes we have drawn, so an accepted delivery can take its route with it.
    var routeLayer = [];
    var mapRef = null;

    function number(value) {
        var parsed = parseFloat(value);
        return isNaN(parsed) ? null : parsed;
    }

    function showMapNotice(selector) {
        var notice = document.querySelector(selector);
        if (notice) {
            notice.hidden = false;
        }
    }

    function hideMapNotice(selector) {
        var notice = document.querySelector(selector);
        if (notice) {
            notice.hidden = true;
        }
    }

    function drawRoutes() {
        var mapEl = document.getElementById('map');

        // Leaflet (or the routing plugin) could not be loaded. Keep the delivery
        // list fully usable and say so rather than leaving an empty grey box.
        if (typeof L === 'undefined' || typeof L.Routing === 'undefined') {
            hideMapNotice('[data-rb-map-loading]');
            showMapNotice('[data-rb-map-fallback]');
            return;
        }

        if (!mapEl) {
            return;
        }

        var tasks = document.querySelectorAll('.task-item');
        var center = DEFAULT_CENTER;

        if (tasks.length > 0) {
            var firstLat = number(tasks[0].dataset.plat);
            var firstLon = number(tasks[0].dataset.plon);
            if (firstLat !== null && firstLon !== null) {
                center = [firstLat, firstLon];
            }
        }

        var map = L.map(mapEl).setView(center, 12);
        mapRef = map;

        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap'
        }).addTo(map);

        tasks.forEach(function (item) {
            var pLat = number(item.dataset.plat);
            var pLon = number(item.dataset.plon);
            var dLat = number(item.dataset.dlat);
            var dLon = number(item.dataset.dlon);
            var donorName = item.dataset.donor;
            var ngoName = item.dataset.ngo;

            if (pLat === null || pLon === null || dLat === null || dLon === null) {
                return;
            }

            var control = L.Routing.control({
                waypoints: [L.latLng(pLat, pLon), L.latLng(dLat, dLon)],
                router: L.Routing.osrmv1({
                    serviceUrl: 'https://router.project-osrm.org/route/v1'
                }),
                lineOptions: {
                    styles: [{ color: ROUTE_COLOR, opacity: 0.85, weight: 5 }]
                },
                addWaypoints: false,
                draggableWaypoints: false,
                fitSelectedRoutes: true,
                show: false,
                createMarker: function (i, wp) {
                    var label = i === 0
                        ? '<b>Pickup:</b> ' + donorName
                        : '<b>Drop:</b> ' + ngoName;
                    return L.marker(wp.latLng).bindPopup(label);
                }
            }).addTo(map);

            routeLayer.push({ item: item, control: control });
        });

        hideMapNotice('[data-rb-map-loading]');

        // The grid settles after first paint; a second invalidateSize stops
        // Leaflet rendering into a half-measured tile area.
        window.setTimeout(function () {
            map.invalidateSize();
        }, 200);

        window.addEventListener('resize', function () {
            map.invalidateSize();
        });
    }

    // Drop the accepted delivery's route so the map keeps matching the list.
    // Best effort: the card is removed either way, exactly as before.
    function removeRouteFor(item) {
        routeLayer = routeLayer.filter(function (entry) {
            if (entry.item !== item) {
                return true;
            }
            try {
                if (entry.control && typeof entry.control.remove === 'function') {
                    entry.control.remove();
                }
                if (mapRef && entry.control && typeof entry.control.getRoute === 'function') {
                    var route = entry.control.getRoute();
                    ['_line', '_marker', '_backMarker'].forEach(function (key) {
                        if (route && route[key]) {
                            mapRef.removeLayer(route[key]);
                        }
                    });
                }
            } catch (error) {
                /* the route is going away anyway */
            }
            return false;
        });
    }

    function setStat(name, value) {
        var nodes = document.querySelectorAll('[data-rb-stat="' + name + '"]');
        Array.prototype.forEach.call(nodes, function (node) {
            node.textContent = value;
        });
    }

    function refreshCounts() {
        var remaining = document.querySelectorAll('.task-item').length;
        setStat('active', remaining);
        setStat('stops', remaining * 2);

        var empty = document.querySelector('[data-rb-empty]');
        if (empty) {
            empty.hidden = remaining !== 0;
        }
    }

    function setBusy(button, busy) {
        var label = button.querySelector('[data-rb-label]');
        var spinner = button.querySelector('[data-rb-spinner]');

        if (spinner) {
            spinner.hidden = !busy;
        }
        if (label) {
            label.textContent = busy ? 'Accepting\u2026' : 'Accept delivery';
        }
        button.disabled = busy;
        button.setAttribute('aria-busy', busy ? 'true' : 'false');
    }

    function bindAccept() {
        var list = document.querySelector('[data-rb-accept-url]');
        if (!list) {
            return;
        }

        var acceptUrl = list.dataset.rbAcceptUrl;

        list.addEventListener('click', function (event) {
            var button = event.target.closest('[data-rb-accept]');
            if (!button || button.disabled) {
                return;
            }

            var foodId = button.dataset.rbAccept;
            var card = button.closest('.task-item');
            setBusy(button, true);

            fetch(acceptUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': RB.getCSRF()
                },
                body: JSON.stringify({ food_id: foodId })
            })
                .then(function (response) {
                    // A CSRF rejection or server error can come back as HTML, so
                    // check the status before assuming a JSON body.
                    return response.json()
                        .catch(function () {
                            return { success: false, error: describeStatus(response) };
                        })
                        .then(function (data) {
                            return { ok: response.ok, data: data };
                        });
                })
                .then(function (result) {
                    if (result.ok && result.data && result.data.success) {
                        if (card) {
                            removeRouteFor(card);
                            card.remove();
                        }
                        refreshCounts();
                        RB.toast(result.data.message || 'Delivery accepted.', 'success');
                    } else {
                        setBusy(button, false);
                        RB.toast(
                            (result.data && result.data.error)
                                || 'Could not accept the delivery.',
                            'error'
                        );
                    }
                })
                .catch(function () {
                    setBusy(button, false);
                    RB.toast('Network error occurred.', 'error');
                });
        });
    }

    function describeStatus(response) {
        if (response.status === 403) {
            return 'Your session expired. Please reload the page and try again.';
        }
        if (response.status >= 500) {
            return 'The server could not process that request.';
        }
        return 'Could not accept the delivery.';
    }

    document.addEventListener('DOMContentLoaded', function () {
        drawRoutes();
        bindAccept();
        refreshCounts();
    });
}());
