/** 
 * Javascript code for the Project Conversational Agents course.
 * 
 * This code makes some basic assumptions about the interaction protocol:
 * - User always is the first to say something (by turning on the microphone)
 * - The microphone automatically is closed again when a transcript has been received (the user has said something)
 * - After receiving a transcript, the turn is given to the agent and the user cannot turn on the microphone.
 * - When the agent has said something, the turn is handed back to the user.
 * 
 * This code also makes assumptions about the names of two buttons: the 'start' and 'mic'(rophone) button.
 * Button clicks are passed on to the webserver, which passes them on to the MARBEL agent using an EIS connector.
 * 
 * Finally, on pages where there is a microphone, a footer should be present with a <p> element with id="transcript".
 * This element will be used to display the transcript received from the ASR component.
 * 
 * SocketIO is used to communicate with the server.
*/

"use strict";

// Establish a WebSocket connection with the Flask server
var socket = io();

// Flag to keep track of whose turn it is (true --> user, false --> agent)
var usersturn = true;

// Code for handling button elements on page
var elements = document.getElementsByClassName("btn");

// Send button clicks to server
var sendButtonClick = function() {
    var name = this.getAttribute("id");
    socket.emit('buttonClick', name); // send button name to web server
};

for (var i = 0; i < elements.length; i++) {
    elements[i].addEventListener('click', sendButtonClick, false);
}

// Dedicated event listeners for two SPECIAL BUTTONS: the 'start' and 'mic' buttons.
// Event listener for the start button (only on the start webpage, so may not be on the current webpage)
var startButton = document.getElementById('start');

if (startButton) {
    startButton.addEventListener('click', function() {
        window.location.href = "recipe_overview.html"
    });
}

// Event listener for the microphone button to toggle from off to on
// (socket handler for 'transcript' event turns it off again, see below)
var micButton = document.getElementById('mic');

if (micButton) {
    micButton.addEventListener('click', function() {
        if (usersturn) {
            document.getElementById('micimg').src  = 'static/images/mic_on.png';
        } else {
            alert("It is not your turn.")
        }
    });
}

// Event handler for successful connection
socket.on('connect', function() {
    console.log('Connected to the server.');
});

// Event handler for connection errors
socket.on('connect_error', function(error) {
    console.log('Connection error:', error);
});

// Event handler for disconnection
socket.on('disconnect', function() {
    console.log('Disconnected from the server.');
});

// Event handler for transcript event
socket.on("transcript", (text) => {
    document.getElementById("transcript").innerHTML = text;
    // when a transcript has been received, the microphone icon should be changed again to indicate the mic has been closed
    document.getElementById('micimg').src  = 'static/images/mic_out.png';
    // User has just said something, so now it is the agent's turn to respond
    usersturn = false;
});

// Event handler for switching turns
socket.on("switchturn", () => {
    usersturn = !usersturn;
})