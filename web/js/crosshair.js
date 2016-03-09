/*
 *  crosshair.js - v0.1.0
 *  Crosshair any dom element.
 *  https://github.com/eschmar/crosshair
 *
 *  @author:   Marcel Eschmann, @eschmar
 *  @license:  MIT License
 */
 
;(function ( $, window, document, undefined ) {
    // set default config
    var coords, live_coords, pct, live_pct, scl, live_scl, legend, marker, defaults = {
        wrap: true,
        legend: true,
		singleaxismode: {on: false, axis: ''},
		axisnames: {x: 'X', y:'Y'},
		axisscale: {x: 1, y: 1},
		axisscaleunit: {x: '', y:''},
		axisscalelegend: false,
		axisscaleinvert: {x: false, y: false},
        marker: '<div class="crosshair-marker"></div>',
        callback: function(crosshair) { console.log(crosshair.pct);	}
    };

    // constructor
    function Plugin(element, options){
        this.options = $.extend({}, defaults, options);
        this._defaults = defaults;
        if (this.options.wrap) {
            $(element).wrap('<div class="crosshair"></div>');
            this.element = $(element).parent();
        }else {
            this.element = $(element).addClass('crosshair');
        }
        this.coords = {x: null, y: null};
        this.live_coords = {x: null, y: null};
        this.pct = {x: null, y: null};
        this.live_pct = {x: null, y: null};
		this.scl = {x: null, y: null};
		this.live_scl = {x: null, y: null};
		
        this.init();
    }

    Plugin.prototype = {
        init: function() {
            var app = this;
            this.spawnCrosshair();

            // hide crosshair and legend onmouseleave
            this.element.hover(function() {
                app.element.find('.hair, .crosshair-legend').show();
            }, function() {
                app.element.find('.hair, .crosshair-legend').hide();
            });
        },

        spawnCrosshair: function() {
            			
			if (!this.options.singleaxismode.on) {
				this.element.append('<div class="hair hair-vertical"></div>');
				this.element.append('<div class="hair hair-horizontal"></div>');
			}
			else
			{
				if (this.options.singleaxismode.axis=='y') { this.element.append('<div class="hair hair-horizontal"></div>'); }
				if (this.options.singleaxismode.axis=='x') { this.element.append('<div class="hair hair-vertical"></div>'); }
			}
            this.initCrosshair();
        },

        initCrosshair: function() {
            var app = this;
            $(this.element).on('mousemove touchmove', function(event) {
                // calculate relative position
                var offset, left, top;
                offset = app.element.offset();
                left = event.pageX - offset.left;
                top = event.pageY - offset.top;

                // update position
                app.live_coords.x = left;
                app.live_coords.y = top;
                
								
				if (!app.options.singleaxismode.on) {
					app.element.find('.hair.hair-horizontal').css('top', top);
					app.element.find('.hair.hair-vertical').css('left', left);
				}
				else
				{
					if (app.options.singleaxismode.axis=='y') {app.element.find('.hair.hair-horizontal').css('top', top); }
					if (app.options.singleaxismode.axis=='x') {app.element.find('.hair.hair-vertical').css('left', left); }
				}
				
				
                // convert to percentages
                app.live_pct.x = ((100 / app.element.width())*app.live_coords.x).toFixed(2);
                app.live_pct.y = ((100 / app.element.height())*app.live_coords.y).toFixed(2);
				
				// convert to scale
                app.live_scl.x = ((app.live_pct.x/100)*app.options.axisscale.x).toFixed(2);
                app.live_scl.y = ((app.live_pct.y/100)*app.options.axisscale.y).toFixed(2);
				
				// scale axis inverted?
				if (app.options.axisscaleinvert.x) { app.live_scl.x = (app.options.axisscale.x-app.live_scl.x).toFixed(2); }
				if (app.options.axisscaleinvert.y) { app.live_scl.y = (app.options.axisscale.y-app.live_scl.y).toFixed(2); }

                app.updateLegend();
                event.stopPropagation();
            });

            this.element.click(function(event) {
                app.setMarker();
                event.stopPropagation();
            });
        },

        updateLegend: function() {
            if (!this.options.legend) {
                this.element.find('.crosshair-legend').remove();
                this.legend = null;
                return;
            };

            if (!this.legend) {
                this.element.append('<div class="crosshair-legend"></div>');
                this.legend = this.element.find('.crosshair-legend');
            };
			
			if (this.options.axisscalelegend) {
			
				if (!this.options.singleaxismode.on) {
					this.legend.html(this.options.axisnames.x+': '+this.live_scl.x+this.options.axisscaleunit.x+', '+this.options.axisnames.y+': '+this.live_scl.y+this.options.axisscaleunit.y);
					}
					else
					{ 
					if (this.options.singleaxismode.axis=='y') {this.legend.html(this.options.axisnames.y+': '+this.live_scl.y+this.options.axisscaleunit.y);}
					if (this.options.singleaxismode.axis=='x') {this.legend.html(this.options.axisnames.x+': '+this.live_scl.x+this.options.axisscaleunit.x);}
					}
			}
			else
			{	if (!this.options.singleaxismode.on) {
					this.legend.html(this.options.axisnames.x+': '+this.live_pct.x+'%, '+this.options.axisnames.y+': '+this.live_pct.y+'%');
					}
					else
					{
					if (this.options.singleaxismode.axis=='y') {this.legend.html(this.options.axisnames.y+': '+this.live_pct.y+'%');}
					if (this.options.singleaxismode.axis=='x') {this.legend.html(this.options.axisnames.x+': '+this.live_pct.x+'%');}
					}
			};
			    
        },

        setMarker: function() {
            // check for multiple or preset markers
            if (this.element.find('.crosshair-marker').length > 1) {
                this.element.find('.crosshair-marker').remove();
                this.marker = null;
            }else if (!this.marker && this.element.find('.crosshair-marker').length === 1) {
                this.marker = this.element.find('.crosshair-marker');
            };

            // inject new marker
            if (!this.marker) {
                this.element.append(this.options.marker);
                this.marker = this.element.find('.crosshair-marker');
            };

            // update coordinates
            this.coords.x = this.live_coords.x;
            this.coords.y = this.live_coords.y;

            // update percentages
            this.pct.x = ((100 / this.element.width())*this.coords.x).toFixed(2);
            this.pct.y = ((100 / this.element.height())*this.coords.y).toFixed(2);
			
			// update scale
			this.scl.x = (this.pct.x/100*this.options.axisscale.x).toFixed(2);
            this.scl.y = (this.pct.y/100*this.options.axisscale.y).toFixed(2);
			
			// scale axis inverted?
			if (this.options.axisscaleinvert.x) { this.scl.x = (this.options.axisscale.x-this.scl.x).toFixed(2); }
			if (this.options.axisscaleinvert.y) { this.scl.y = (this.options.axisscale.y-this.scl.y).toFixed(2); }
    
            // update marker position
            var width = this.marker.width();
            var height = this.marker.height();
            this.marker.css('left', this.coords.x-(width/2));
            this.marker.css('top', this.coords.y-(height/2));
			
			//set markers coordinate text
			//this.marker.html(this.scl.x+'/'+this.scl.y);

            // trigger callback
            this.options.callback(this);
        }
    }

    // lightweight plugin wrapper, preventing against multiple instantiations
    $.fn["crosshair"] = function (options) {
        return this.each(function() {
            if (!$.data(this, "crosshair")) {
                $.data(this, "crosshair", new Plugin(this, options))
            };
        });
    };
})( jQuery, window, document );