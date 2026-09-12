# RideMesh — cyan UI refresh

Reference: the three-screen RideMesh image supplied on September 11, 2026.

## Source baseline

GitHub: kabeer1238/RideMesh, branch production-vc31-approved-ui-billing, commit 6516195e322778bff59b343859d217d0a2a76bef.

This package contains the materialized production source. The repository's production workflow applies a sequence of migration scripts at build time; those migrations have already been applied here. Build the project directly. Do not rerun the older migration scripts over the redesigned source.

## Changes

- Dark cyan palette, outlined live card, white/cyan active ride title, red end control, compact action cards.
- Cinematic road splash with the existing RideMesh logo and real package version.
- Helmet photo behind the active ride header, with a dark fade for text contrast.
- Vector helmet avatars and drawn signal bars driven by existing transport quality.
- Three live rider rows on the ride overview. The Riders navigation item opens a full, scrollable list of actual participants, plus invite and rider-detail actions.
- Connecting and microphone-muted labels reflect app state. No sample riders or fabricated offline states are added to the live app.
- Existing ride, microphone, invitation, map, settings, subscription, and transport logic retained from the materialized production baseline.

## Build and install

Use JDK 17, Gradle 8.13, Android SDK 36. Set the SDK location in a local.properties file or ANDROID_HOME.

    ./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug

The debug launcher opens a design preview with clearly labeled sample riders, working Ride/Riders navigation, and a microphone-state toggle. It does not open an audio or location session. Settings → Open App enters the real app flow, including the new splash. The preview activity exists only in src/debug and is excluded from release builds.

Debug uses application ID in.autopilotindia.ridemesh.preview and label RideMesh Preview. It is a separate app with its own local settings and does not replace the installed production app. Both source and debug preview retain version 1.0.2 / code 31 as requested. Production retains application ID in.autopilotindia.ridemesh. The debug preview has a separate application ID.

Billing is retained. A sideloaded debug application with a different application ID is not a Play subscription validation build. Google Maps requires the project's MAPS_API_KEY and matching package/certificate configuration. No signing keys or Maps API credentials are included in this source package.

The source package omits old CI workflows and migration scripts to prevent them from overwriting this UI. Configure release signing and release CI separately when preparing the production package.

## Artwork

Generated with the built-in image-generation tool. Both assets are copied into app/src/main/res/drawable-nodpi and are included in this package. The existing RideMesh brand artwork is retained. Helmet avatars are Android vector resources.

Road asset: rm_road.png
Prompt: Create a cinematic photorealistic background asset for the RideMesh motorcycle app splash screen. Portrait 1024x1536. A winding mountain road at night with elegant luminous electric cyan light trails along its curves, rocky dark mountain valley, moody nearly black teal sky. The winding road fills the lower two thirds, with the top third very dark softly clouded negative space for a logo to be overlaid in the app. Premium dramatic photographic realism, deep black and cool cyan palette. No text, no lettering, no logo, no phone frame, no interface, no borders. Full bleed.

Helmet asset: rm_helmet_photo.png
Prompt: Use case: photorealistic-natural. Asset: landscape background for RideMesh active ride header. Cinematic close-up of a motorcyclist in a glossy black full-face helmet and dark riding jacket, seated on motorcycle, head and shoulder on far right half of composition, facing left. Mirror silhouette lower left. Stormy dark teal sky and mountains blurred behind. Nearly black palette, subtle cyan reflections on visor edges. Left half mostly dark empty space for UI text overlay. Premium realistic motorcycle photography, understated atmospheric contrast. Landscape 1536x1024. No text, no logos, no watermarks, no UI, no frames.
