use proc_macro::TokenStream;
use quote::TokenStreamExt;
use syn::{parse_macro_input, DeriveInput};

mod config;

#[proc_macro_derive(MultiWidgetConfig, attributes(child_only))]
pub fn multi_widget_config_derive(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let mut tokens = proc_macro2::TokenStream::new();
    tokens.append_all(config::derive_multi_widget_config_main(input.clone()));
    tokens.append_all(config::derive_multi_widget_config_de_main(input.clone()));
    tokens.into()
}

#[proc_macro_derive(OptDeserializeConfig, attributes(deserialize_struct))]
pub fn opt_deserialize_derive(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let mut tokens = proc_macro2::TokenStream::new();
    // tokens.append_all(config::derive_multi_widget_config_main(input.clone()));
    tokens.append_all(config::derive_config_de(input.clone()));
    tokens.into()
}
