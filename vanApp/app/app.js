'use strict';


// Declare app level module which depends on filters, and services
var app = angular.module('txiRushApp', [
  'ngRoute',
  'txiRushApp.filters',
  'txiRushApp.services',
  'txiRushApp.directives',
]);
app.
config(['$routeProvider', function($routeProvider) {
  $routeProvider.when('/events', {
      templateUrl: 'routes/events/events.html', 
      controller: 'eventsController'
  });
  $routeProvider.when('/vantracker', {
      templateUrl: 'routes/vanTracker/vanTracker.html', 
      controller: 'vanController'
  });
  $routeProvider.when('/brothers', {
      templateUrl: 'routes/brothers/brothers.html', 
      controller: 'brothersController'
  });
  $routeProvider.when('/info', {
      templateUrl: 'routes/info/info.html', 
      controller: 'infoController'
  });
  $routeProvider.when('/driving', {
      templateUrl: 'routes/driving/driving.html', 
      controller: 'drivingController'
  });
  $routeProvider.when('/coordinate', {
      templateUrl: 'routes/coordinate/coordinate.html', 
      controller: 'coordinateController'
  });
  $routeProvider.when('/vanRequest', {
      templateUrl: 'routes/vanRequest/vanRequest.html', 
      controller: 'requestController'
  });
  $routeProvider.when('/me', {
      templateUrl: 'routes/me/me.html', 
      controller: 'meController'
  });
  $routeProvider.otherwise({redirectTo: '/events'});
}]);

app.controller("AppController", function($scope, $rootScope, $http, $route, $location){

    //default the menu to not show
    $rootScope.showmenu=false;
    $rootScope.requesting=false;
    $rootScope.notLogged = true;
    $scope.$route=$route;
    $scope.$location=$location;

    $rootScope.serve = function(destination){
      return "https://rushtxi.mit.edu/app/api/" + destination;
    };

    //download brother data
    var brotherPromise = $http.get($rootScope.serve("/brothers"));
    // var brotherPromise = $http.get("local_data/brothers.json");
    $("#loader").show();
    brotherPromise.success(function(data, status, headers, config){
        $rootScope.brothers = data.brothers;
        $rootScope.drivers = [];
        for (var i=0; i<$rootScope.brothers.length; i++){
          if (data.brothers[i].driver){
            $rootScope.drivers.push(data.brothers[i]);
          }
        }
        $("#loader").hide();
    });
    brotherPromise.error(function(data, status, headers, config){
        $("#loader").hide();
    });
    
    // get user data
    var userPromise = $http.get($rootScope.serve("me"));
    userPromise.success(function(data, status, headers, config){
        $rootScope.me = data.me;
        $rootScope.isCoordinator = data.me.coordinator;
        $rootScope.isRushee = data.me.rushee;
        $rootScope.isBrother = data.me.brother;
        if (!$rootScope.isRushee && !$rootScope.isBrother){
          $scope.$location.path('/me');
        }
    });

    //Load Event Data
   var eventPromise = $http.get("https://rushtxi.mit.edu/app/api/events");
    // var eventPromise = $http.get("local_data/events.json");
    $("#loader").show();
    eventPromise.success(function(data, status, headers, config){
        $rootScope.days = data.days;
        $("#loader").hide();
    });

    //this is the toggle function
    $rootScope.toggleMenu = function(){
        $rootScope.showmenu=($rootScope.showmenu) ? false : true;
        $("#loader").hide();
    };
    $rootScope.closeMenu = function(){
        if ($rootScope.showmenu === true){
           $rootScope.showmenu=false;
        }
    };
    $rootScope.back = function(){
      $rootScope.requesting=false;
    }

    $rootScope.setPath = function(path){
        $rootScope.returnPath=path;
    };

    $("#window").ready(function() {
            // Animate loader off screen
            $("#loader").hide();
    });

});
