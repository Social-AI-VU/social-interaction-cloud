Getting started with the Nao
=================================================

Ground Rules
----------------------------

1. Handle with care.
    a. Use two hands to carry. Best place tho hold is its chest.
    b. The fingers are brittle. Make sure when stowing the Nao away to put the hands in a safe spot.

2. Always put the Nao on a large surface, preferably the ground.
    a. The crouch and sitting positions are stable.
    b. It can stand by itself from those positions.

3. Make sure the Nao is in rest mode when its idle (e.g. when you are programming).
    a. From code: call self.nao.autonomous.request(NaoRestRequest())
    b. Via Robot: press its chest button twice to switch between rest and alive mode.

4. Keep the Nao charged.

Base functionalities
----------------------------

The main available functionalities are:

1. Accessing microphone, camera, and button streams.
2. Text-to-Speech (plain and animated).
3. Playing out-of-the-box motions and gestures.
4. Recording and playing custom motions.
5. LED control.

For a full overview of the available functionalities read the API references :doc:`api/device_components` (NAOqi Components)
and the documentation from the Nao manufacturer: http://doc.aldebaran.com/2-8/naoqi/index.html.

📹: Video
----------------------------

   .. raw:: html

        <iframe width="560" height="315" src="https://www.youtube.com/embed/_CbWBzBkAXs?si=n30ishby-nsf_pzT" title="YouTube video player" frameborder="0" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" referrerpolicy="strict-origin-when-cross-origin" allowfullscreen></iframe>
        
Relevant Tutorials
----------------------------
For information on how to get started with the Nao, please consult the tutorials section: :doc:`tutorials/4_motion`

