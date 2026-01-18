use std::collections::HashMap;

use quote::{format_ident, quote, TokenStreamExt};
use syn::{Data, DeriveInput, Field, Type};

pub fn derive_multi_widget_config_main(input: DeriveInput) -> proc_macro2::TokenStream {
    let DeriveInput {
        ident, data, vis, ..
    } = input;
    let ident_main = format_ident!("{}Main", &ident);
    let mut main_fields = Vec::new();
    let mut main_fields_ident = Vec::new();
    let mut main_fields_child_only_ident = Vec::new();
    if let Data::Struct(ds) = data {
        for field in ds.fields.iter() {
            if field
                .attrs
                .iter()
                .any(|attr| attr.path().is_ident("child_only"))
            {
                main_fields_child_only_ident.push(field.ident.clone().unwrap());
                continue;
            }
            let Field {
                attrs,
                vis: _,
                mutability: _,
                ident,
                colon_token,
                ty,
            } = field;
            let attrs = attrs
                .iter()
                .filter(|attr| !attr.path().is_ident("deserialize_struct"))
                .filter(|attr| {
                    if attr.path().is_ident("serde") {
                        let skip_ser = attr
                            .parse_nested_meta(|attr| {
                                if attr.path.is_ident("skip_serializing") {
                                    Err(attr.error("skip_ser"))
                                } else {
                                    Ok(())
                                }
                            })
                            .is_err();
                        return !skip_ser;
                    }
                    true
                });
            main_fields_ident.push(ident.clone().unwrap());
            let field = quote! {
                #(#attrs)*
                pub(crate) #ident #colon_token #ty
            };
            main_fields.push(field);
        }
    }
    // create ConfigMain struct
    let mut config_main_struct = quote! {
        #[derive(Debug, Clone, serde::Serialize)]
        #vis struct #ident_main {
            #(#main_fields,)*
            pub(crate) windows: ::std::collections::HashMap<String, Vec<#ident>>
        }
    };
    let config_main_impl = quote! {
        impl #ident_main {
            pub fn default_conf(&self) -> #ident{
                let child_default = #ident::default();
                #ident{
                    #(#main_fields_ident: self.#main_fields_ident.clone(),)*
                    #(#main_fields_child_only_ident: child_default.#main_fields_child_only_ident,)*
                }
            }
            pub fn get_for_window(&self, window: &str, idx: usize) -> #ident{
                if let Some(conf) = self.windows.get(window){
                    if let Some(conf) = conf.get(idx){
                        return conf.clone();
                    }
                }
                self.default_conf()
            }
        }
        impl ::std::default::Default for #ident_main {
            fn default() -> Self {
                let mut map = ::std::collections::HashMap::new();
                // map.insert("".to_string(), vec![#ident::default()]);
                let child_default = #ident::default();
                Self {
                    #(#main_fields_ident: child_default.#main_fields_ident,)*
                    windows: map,
                }
            }
        }
    };
    config_main_struct.append_all(config_main_impl);
    config_main_struct
}

pub fn derive_config_de(input: DeriveInput) -> proc_macro2::TokenStream {
    let DeriveInput {
        ident, data, vis, ..
    } = input;
    let ident_de = format_ident!("De{}", &ident);
    let mut opt = HashMap::new();
    let mut opt_de_struct = HashMap::new();
    if let Data::Struct(ds) = data {
        for field in ds.fields.iter() {
            let deserialize_attr = field
                .attrs
                .iter()
                .find(|attr| attr.path().is_ident("deserialize_struct"));
            let Field {
                attrs,
                vis: _,
                mutability: _,
                ident,
                colon_token,
                ty,
            } = field;
            let ty = match deserialize_attr {
                Some(attr) => {
                    let ty: Type = attr
                        .parse_args()
                        .expect("error parsing deserialize_struct attribute");
                    ty
                }
                None => ty.clone(),
            };
            let attrs = attrs.iter().filter(|attr| {
                !(attr.path().is_ident("deserialize_struct") || attr.path().is_ident("child_only"))
            });
            let field = quote! {
                #(#attrs)*
                pub(crate) #ident #colon_token ::std::option::Option<#ty>
            };
            if deserialize_attr.is_some() {
                opt_de_struct.insert(ident.clone().unwrap(), field);
            } else {
                opt.insert(ident.clone().unwrap(), field);
            }
        }
    }
    let opt_fields = opt.values();
    let opt_de_struct_fields = opt_de_struct.values();
    let mut de_config_struct = quote! {
        #[derive(Debug, Clone, Default, serde::Deserialize)]
        #[serde(default)]
        #vis struct #ident_de{
            #(#opt_fields,)*
            #(#opt_de_struct_fields,)*
        }

    };
    let opt_ident = opt.keys();
    let opt_de_struct_ident = opt_de_struct.keys();
    let opt_de_struct_ident1 = opt_de_struct.keys();
    let de_config_impl = quote! {
        impl #ident_de {
            pub fn into_config(self, default: &#ident) -> #ident {
                #(let #opt_de_struct_ident = match self.#opt_de_struct_ident{
                    Some(val) => val.into_config(&default.#opt_de_struct_ident),
                    None => default.#opt_de_struct_ident.clone(),
                };)*
                #ident{
                    #(#opt_ident: self.#opt_ident.unwrap_or(default.#opt_ident.clone()),)*
                    #(#opt_de_struct_ident1: #opt_de_struct_ident1,)*
                }
            }
        }
    };
    de_config_struct.append_all(de_config_impl);
    de_config_struct
}

pub fn derive_multi_widget_config_de_main(input: DeriveInput) -> proc_macro2::TokenStream {
    let DeriveInput {
        ident, data, vis, ..
    } = input;
    let ident_main_de = format_ident!("De{}Main", &ident);
    let ident_main = format_ident!("{}Main", &ident);
    let ident_de = format_ident!("De{}", &ident);
    let mut fields_ident = Vec::new();
    let mut fields = Vec::new();
    let mut child_fields_ident = Vec::new();
    let mut child_fields = Vec::new();
    let mut de_struct_fields_ident = Vec::new();
    if let Data::Struct(ds) = data {
        for field in ds.fields.iter() {
            let child_only_attr = field
                .attrs
                .iter()
                .find(|attr| attr.path().is_ident("child_only"));
            let deserialize_attr = field
                .attrs
                .iter()
                .find(|attr| attr.path().is_ident("deserialize_struct"));
            let Field {
                attrs,
                vis: _,
                mutability: _,
                ident,
                colon_token,
                ty,
            } = field;
            let attrs = attrs.iter().filter(|attr| {
                !attr.path().is_ident("deserialize_struct") && !attr.path().is_ident("child_only")
            });
            let field = quote! {
                #(#attrs)*
                pub(crate) #ident #colon_token #ty
            };
            if child_only_attr.is_some() {
                child_fields_ident.push(ident.clone().unwrap());
                child_fields.push(field);
            } else {
                if deserialize_attr.is_some() {
                    de_struct_fields_ident.push(ident.clone().unwrap());
                } else {
                    fields_ident.push(ident.clone().unwrap());
                }
                fields.push(field);
            }
        }
    }
    // create ConfigMain struct
    let de_struct_fields_ident1 = de_struct_fields_ident.clone();
    let mut config_main_struct = quote! {
        #[derive(Debug, Clone, serde::Deserialize)]
        #[serde(default)]
        #vis struct #ident_main_de {
            #(#fields,)*
            pub(crate) windows: ::std::collections::HashMap<String, Vec<#ident_de>>
        }
        impl ::std::default::Default for #ident_main_de {
            fn default() -> Self {
                let map = ::std::collections::HashMap::new();
                let child_default = #ident::default();
                Self {
                    #(#fields_ident: child_default.#fields_ident,)*
                    #(#de_struct_fields_ident1: child_default.#de_struct_fields_ident,)*
                    windows: map,
                }
            }
        }
    };

    let de_struct_fields_ident2 = de_struct_fields_ident.clone();
    let config_main_impl = quote! {
        impl #ident_main_de {
            pub fn into_main_config(self) -> #ident_main {
                let mut windows = ::std::collections::HashMap::new();
                let mut main_conf = #ident_main{
                    #(#fields_ident: self.#fields_ident,)*
                    #(#de_struct_fields_ident: self.#de_struct_fields_ident,)*
                    windows: ::std::collections::HashMap::new(),
                };
                let child_default = main_conf.default_conf();
                for (name, opt_vec_conf) in self.windows {
                    let mut vec_conf = Vec::new();
                    for opt_conf in opt_vec_conf {
                        let conf = #ident {
                            #(#fields_ident: opt_conf.#fields_ident.unwrap_or(main_conf.#fields_ident.clone()),)*
                            #(#de_struct_fields_ident2: opt_conf.#de_struct_fields_ident1.unwrap_or_default().into_config(&main_conf.#de_struct_fields_ident1),)*
                            #(#child_fields_ident: opt_conf.#child_fields_ident.unwrap_or(child_default.#child_fields_ident.clone()),)*
                        };
                        vec_conf.push(conf);
                    }
                    windows.insert(name, vec_conf);
                }
                main_conf.windows = windows;
                main_conf
            }
        }
    };
    config_main_struct.append_all(config_main_impl);
    config_main_struct
}
