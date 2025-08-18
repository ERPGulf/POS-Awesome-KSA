import mitt from 'mitt';
// export const evntBus = mitt();
export default {
    install: (app, options) => {
        app.config.globalProperties.__ = window.__;
        app.config.globalProperties.frappe = window.frappe;
        app.config.globalProperties.eventBus = mitt();
    }
}

