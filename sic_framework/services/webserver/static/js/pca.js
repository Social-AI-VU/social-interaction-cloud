"use strict";

// Establish a WebSocket connection with the Flask server
var socket = io();

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
});
    