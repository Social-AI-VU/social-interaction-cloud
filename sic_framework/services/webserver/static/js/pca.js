"use strict";

// Establish a WebSocket connection with the Flask server
var socket = io();

// Code for handling button elements on page
var elements = document.getElementsByClassName("btn");

var handleButtonClick = function() {
  var name = this.getAttribute("name");
  socket.emit('clicked_flag', name); // send button name to web server
};

for (var i = 0; i < elements.length; i++) {
  elements[i].addEventListener('click', handleButtonClick, false);
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